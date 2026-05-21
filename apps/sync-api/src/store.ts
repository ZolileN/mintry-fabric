import fs from "node:fs";
import path from "node:path";

export interface MandateRecord {
  id: string;
  budget_usd: number;
  spent_usd: number;
  status: "active" | "exhausted" | "expired";
  expires_at: string | null;
}

export interface AuditEvent {
  id: number;
  timestamp: string;
  mandate_id: string;
  action: string;
  amount: number;
  details: string;
}

interface StoreState {
  nextAuditId: number;
  mandates: Record<string, MandateRecord>;
  history: AuditEvent[];
}

const DEFAULT_STORE_PATH = path.join("/tmp", "mintry-sync-store.json");

function getStorePath(): string {
  return process.env.MINTRY_SYNC_STORE_PATH || DEFAULT_STORE_PATH;
}

function createEmptyState(): StoreState {
  return {
    nextAuditId: 1,
    mandates: {},
    history: [],
  };
}

function loadState(): StoreState {
  const storePath = getStorePath();
  if (!fs.existsSync(storePath)) {
    return createEmptyState();
  }

  try {
    const raw = fs.readFileSync(storePath, "utf8");
    const parsed = JSON.parse(raw) as Partial<StoreState>;
    return {
      nextAuditId: parsed.nextAuditId ?? 1,
      mandates: parsed.mandates ?? {},
      history: parsed.history ?? [],
    };
  } catch {
    return createEmptyState();
  }
}

function saveState(state: StoreState): void {
  const storePath = getStorePath();
  fs.mkdirSync(path.dirname(storePath), { recursive: true });
  fs.writeFileSync(storePath, JSON.stringify(state, null, 2));
}

function roundUsd(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export class SyncStore {
  private state: StoreState;

  constructor() {
    this.state = loadState();
  }

  private addAuditEvent(
    mandateId: string,
    action: string,
    amount: number,
    details: string,
  ): void {
    this.state.history.push({
      id: this.state.nextAuditId++,
      timestamp: new Date().toISOString(),
      mandate_id: mandateId,
      action,
      amount: roundUsd(amount),
      details,
    });
  }

  private getOrCreateMandate(id: string): MandateRecord {
    const existing = this.state.mandates[id];
    if (existing) {
      return existing;
    }

    const created: MandateRecord = {
      id,
      budget_usd: 0,
      spent_usd: 0,
      status: "active",
      expires_at: null,
    };
    this.state.mandates[id] = created;
    return created;
  }

  upsertMandate(id: string, budgetUsd: number, expiresAt: string | null): MandateRecord {
    const existing = this.state.mandates[id];
    if (!existing) {
      this.state.mandates[id] = {
        id,
        budget_usd: roundUsd(budgetUsd),
        spent_usd: 0,
        status: "active",
        expires_at: expiresAt,
      };
      this.addAuditEvent(
        id,
        "create",
        budgetUsd,
        `Created with budget ceiling $${roundUsd(budgetUsd).toFixed(4)}${expiresAt ? ` and expiry ${expiresAt}` : ""}`,
      );
    } else {
      existing.budget_usd = roundUsd(budgetUsd);
      existing.expires_at = expiresAt;
      existing.status = "active";
      this.addAuditEvent(
        id,
        "update",
        budgetUsd,
        `Updated budget ceiling to $${roundUsd(budgetUsd).toFixed(4)}${expiresAt ? ` and expiry ${expiresAt}` : ""}`,
      );
    }

    saveState(this.state);
    return this.state.mandates[id];
  }

  revokeMandate(id: string): MandateRecord {
    const mandate = this.getOrCreateMandate(id);
    mandate.status = "exhausted";
    this.addAuditEvent(id, "exhaust", 0, "Mandate marked as exhausted");
    saveState(this.state);
    return mandate;
  }

  recordSync(input: { mandateId: string; spend?: number; tokens?: number }): MandateRecord {
    const mandate = this.getOrCreateMandate(input.mandateId);
    const spend = roundUsd(input.spend ?? 0);
    mandate.spent_usd = roundUsd(mandate.spent_usd + spend);

    if (mandate.budget_usd > 0 && mandate.spent_usd >= mandate.budget_usd) {
      mandate.status = "exhausted";
    }

    this.addAuditEvent(
      input.mandateId,
      "spend",
      spend,
      `Synced spend${input.tokens ? ` (${input.tokens} tokens)` : ""}`,
    );

    saveState(this.state);
    return mandate;
  }

  getSummary(): {
    stats: {
      total_mandates: number;
      total_budget: number;
      total_spent: number;
      remaining_headroom: number;
    };
    top_mandates: Array<{ id: string; spent_usd: number }>;
    mandates: Array<MandateRecord & { remaining_headroom: number }>;
    history: AuditEvent[];
  } {
    const mandates = Object.values(this.state.mandates)
      .map((mandate) => ({
        ...mandate,
        remaining_headroom: roundUsd(mandate.budget_usd - mandate.spent_usd),
      }))
      .sort((a, b) => b.spent_usd - a.spent_usd);

    const totalBudget = mandates.reduce((sum, item) => sum + item.budget_usd, 0);
    const totalSpent = mandates.reduce((sum, item) => sum + item.spent_usd, 0);

    return {
      stats: {
        total_mandates: mandates.length,
        total_budget: roundUsd(totalBudget),
        total_spent: roundUsd(totalSpent),
        remaining_headroom: roundUsd(totalBudget - totalSpent),
      },
      top_mandates: mandates.slice(0, 5).map((mandate) => ({
        id: mandate.id,
        spent_usd: mandate.spent_usd,
      })),
      mandates,
      history: [...this.state.history].sort((a, b) => b.id - a.id).slice(0, 100),
    };
  }
}
