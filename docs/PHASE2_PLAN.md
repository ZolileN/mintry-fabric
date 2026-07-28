# Phase 2 Plan — Enterprise

**Status:** In progress (E0 started)  
**Prerequisite:** Phase 1 `v1.0.0` production gate (closed enforce loop)  
**Source:** [`CONTROL_PLANE_SPEC.md`](./CONTROL_PLANE_SPEC.md) §6–§11, [`ROADMAP.md`](./ROADMAP.md), ADR-003  
**Constraint:** All workstreams must obey the [Six Architecture Principles](./ARCHITECTURE.md).

## Goal

Extend Mintry from single-agent local governance to multi-agent fleets and language-agnostic enforcement — without putting network I/O or non-deterministic logic on the hot path.

## Architecture target (Option A fleet)

```text
Author (Dashboard)
        │  fleet_total + partitions {agent → share}
        │  validate sum(shares) ≤ total
        │  for each agent: canonical ES256 sign → INSERT policy_bundles
        ▼
   Supabase control plane (immutable versions per agent)
        │  each agent polls its own agent_id (async)
        ▼
   PolicyCache (verified local max_usd = that agent's share)
        │  synchronous local read only
        ▼
   PolicyEngine.authorize()  ←── no fleet / Redis / OPA on hot path
```

**Option A meaning:** Fleet-wide consistency is achieved by **static partition of the total at author time**. Each agent enforces only its slice. There is no shared atomic counter. Revisit Option B (Redis) only when a true global hard cap is required.

## Workstream map

| ID | Workstream | Depends on | Principle notes |
| --- | --- | --- | --- |
| **E0** | Fleet Option A authoring + validation | v1.0.0 | Author centrally; enforce locally via existing caps |
| **E1** | Agent-grouped ledger (UI) | E0 optional | Presentation only; ledger stays append-only |
| **E2** | Org / project hierarchy (data model) | E0 | Inheritance resolves at sync time into flat caps |
| **E3** | Go sidecar (ADR-003) | E0 | Same local authorize contract; HTTP_PROXY path |
| **E4** | OPA bundle compile-at-sync | E2 | Never invoke OPA on hot path |
| **E5** | Vault alias orchestration | E3 | Secrets never on Mintry servers |

Recommended order: **E0 → E1 → E3 scaffold → E2 → E4/E5**.

## E0 — Fleet Option A (this milestone)

### Deliverables

1. **`mintry.core.fleet`** — pure validation:
   - `validate_partitions(total_usd, partitions) → ok | error`
   - Rules: non-empty map; each share ≥ 0.01; `sum(shares) ≤ total_usd`
2. **Dashboard `POST /api/fleets/partition`** (auth required):
   - Accept `{ fleet_id, total_usd, partitions: { agent_id: share_usd } }`
   - Validate partitions
   - For each agent, sign & insert a policy bundle with mandate rule
     `{ max_usd: share, fleet_id, fleet_total_usd }`
3. **Dashboard UI** — Fleet Partition panel (author once → push N agent policies)
4. **Tests** — partition validation edge cases; reject oversubscribe

### Acceptance

- Oversubscribed fleet (`sum > total`) is rejected before any insert
- Undersubscribed fleet (`sum < total`) is accepted (unallocated headroom)
- Each agent still enforces only local `max_usd` with zero network on authorize
- Existing single-agent Sign & Push remains unchanged

### Out of scope for E0

- Redis / shared counters (Option B)
- Cross-agent spend aggregation on the hot path
- Sidecar binary

## E1 — Agent-grouped ledger

Group mandate rows by `agent_id` (default: mandate id) with rollup budget/spent/policy version. No schema migration required for the first cut.

## E2+ — Later

See ROADMAP Phase 2 checklist. Org hierarchy must compile to flat per-agent numbers before sync (Principle 6). Sidecar must reuse the same authorize semantics as the Python interceptor.
