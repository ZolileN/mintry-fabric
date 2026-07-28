/**
 * Fleet Option A — static sub-budget partitioning (mirrors mintry.core.fleet).
 *
 * sum(shares) ≤ total_usd. Each agent later enforces only its local max_usd.
 */

export const MIN_SHARE_USD = 0.01;
const EPSILON = 1e-9;

export type FleetPartitionError = { ok: false; error: string };
export type FleetPartitionPlan = {
  ok: true;
  fleet_id: string;
  total_usd: number;
  partitions: Record<string, number>;
  allocated_usd: number;
  unallocated_usd: number;
};

export function validatePartitions(
  totalUsd: number,
  partitions: Record<string, number>,
  opts?: { fleetId?: string; minShareUsd?: number }
): FleetPartitionPlan | FleetPartitionError {
  const minShare = opts?.minShareUsd ?? MIN_SHARE_USD;

  if (typeof totalUsd !== "number" || !Number.isFinite(totalUsd)) {
    return { ok: false, error: "total_usd must be a finite number" };
  }
  if (totalUsd < minShare) {
    return {
      ok: false,
      error: `total_usd must be >= ${minShare.toFixed(2)} (got ${totalUsd})`,
    };
  }

  if (!partitions || typeof partitions !== "object" || Array.isArray(partitions)) {
    return {
      ok: false,
      error: "partitions must be an object map of agent_id → share_usd",
    };
  }

  const entries = Object.entries(partitions);
  if (entries.length === 0) {
    return { ok: false, error: "partitions must include at least one agent" };
  }

  const normalized: Record<string, number> = {};
  for (const [rawAgent, rawShare] of entries) {
    const agentId = String(rawAgent ?? "").trim();
    if (!agentId) {
      return { ok: false, error: "every partition key must be a non-empty agent_id" };
    }
    if (typeof rawShare !== "number" || !Number.isFinite(rawShare)) {
      return {
        ok: false,
        error: `share for agent '${agentId}' must be a finite number`,
      };
    }
    if (rawShare < minShare) {
      return {
        ok: false,
        error: `share for agent '${agentId}' must be >= ${minShare.toFixed(2)} (got ${rawShare})`,
      };
    }
    if (agentId in normalized) {
      return { ok: false, error: `duplicate agent_id in partitions: '${agentId}'` };
    }
    normalized[agentId] = Math.round(rawShare * 1e6) / 1e6;
  }

  const allocated =
    Math.round(Object.values(normalized).reduce((a, b) => a + b, 0) * 1e6) / 1e6;
  if (allocated > totalUsd + EPSILON) {
    return {
      ok: false,
      error: `fleet oversubscribed: allocated $${allocated.toFixed(4)} exceeds total $${totalUsd.toFixed(4)}`,
    };
  }

  const total = Math.round(totalUsd * 1e6) / 1e6;
  return {
    ok: true,
    fleet_id: (opts?.fleetId || "").trim(),
    total_usd: total,
    partitions: normalized,
    allocated_usd: allocated,
    unallocated_usd: Math.round(Math.max(total - allocated, 0) * 1e6) / 1e6,
  };
}

export function mandateRuleForShare(
  shareUsd: number,
  opts?: { fleetId?: string; fleetTotalUsd?: number }
): Record<string, unknown> {
  const rule: Record<string, unknown> = {
    max_usd: shareUsd,
    allow: true,
  };
  if (opts?.fleetId) {
    rule.fleet_id = opts.fleetId;
  }
  if (opts?.fleetTotalUsd !== undefined) {
    rule.fleet_total_usd = opts.fleetTotalUsd;
  }
  return rule;
}
