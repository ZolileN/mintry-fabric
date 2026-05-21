"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.SyncStore = void 0;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const DEFAULT_STORE_PATH = node_path_1.default.join("/tmp", "mintry-sync-store.json");
function getStorePath() {
    return process.env.MINTRY_SYNC_STORE_PATH || DEFAULT_STORE_PATH;
}
function createEmptyState() {
    return {
        nextAuditId: 1,
        mandates: {},
        history: [],
    };
}
function loadState() {
    const storePath = getStorePath();
    if (!node_fs_1.default.existsSync(storePath)) {
        return createEmptyState();
    }
    try {
        const raw = node_fs_1.default.readFileSync(storePath, "utf8");
        const parsed = JSON.parse(raw);
        return {
            nextAuditId: parsed.nextAuditId ?? 1,
            mandates: parsed.mandates ?? {},
            history: parsed.history ?? [],
        };
    }
    catch {
        return createEmptyState();
    }
}
function saveState(state) {
    const storePath = getStorePath();
    node_fs_1.default.mkdirSync(node_path_1.default.dirname(storePath), { recursive: true });
    node_fs_1.default.writeFileSync(storePath, JSON.stringify(state, null, 2));
}
function roundUsd(value) {
    return Math.round(value * 10000) / 10000;
}
class SyncStore {
    state;
    constructor() {
        this.state = loadState();
    }
    addAuditEvent(mandateId, action, amount, details) {
        this.state.history.push({
            id: this.state.nextAuditId++,
            timestamp: new Date().toISOString(),
            mandate_id: mandateId,
            action,
            amount: roundUsd(amount),
            details,
        });
    }
    getOrCreateMandate(id) {
        const existing = this.state.mandates[id];
        if (existing) {
            return existing;
        }
        const created = {
            id,
            budget_usd: 0,
            spent_usd: 0,
            status: "active",
            expires_at: null,
        };
        this.state.mandates[id] = created;
        return created;
    }
    upsertMandate(id, budgetUsd, expiresAt) {
        const existing = this.state.mandates[id];
        if (!existing) {
            this.state.mandates[id] = {
                id,
                budget_usd: roundUsd(budgetUsd),
                spent_usd: 0,
                status: "active",
                expires_at: expiresAt,
            };
            this.addAuditEvent(id, "create", budgetUsd, `Created with budget ceiling $${roundUsd(budgetUsd).toFixed(4)}${expiresAt ? ` and expiry ${expiresAt}` : ""}`);
        }
        else {
            existing.budget_usd = roundUsd(budgetUsd);
            existing.expires_at = expiresAt;
            existing.status = "active";
            this.addAuditEvent(id, "update", budgetUsd, `Updated budget ceiling to $${roundUsd(budgetUsd).toFixed(4)}${expiresAt ? ` and expiry ${expiresAt}` : ""}`);
        }
        saveState(this.state);
        return this.state.mandates[id];
    }
    revokeMandate(id) {
        const mandate = this.getOrCreateMandate(id);
        mandate.status = "exhausted";
        this.addAuditEvent(id, "exhaust", 0, "Mandate marked as exhausted");
        saveState(this.state);
        return mandate;
    }
    recordSync(input) {
        const mandate = this.getOrCreateMandate(input.mandateId);
        const spend = roundUsd(input.spend ?? 0);
        mandate.spent_usd = roundUsd(mandate.spent_usd + spend);
        if (mandate.budget_usd > 0 && mandate.spent_usd >= mandate.budget_usd) {
            mandate.status = "exhausted";
        }
        this.addAuditEvent(input.mandateId, "spend", spend, `Synced spend${input.tokens ? ` (${input.tokens} tokens)` : ""}`);
        saveState(this.state);
        return mandate;
    }
    getSummary() {
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
exports.SyncStore = SyncStore;
