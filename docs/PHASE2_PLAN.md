# Phase 2 Plan — Enterprise

**Status:** Complete (E0–E5)  
**Prerequisite:** Phase 1 `v1.0.0` production gate (closed enforce loop)  
**Source:** [`CONTROL_PLANE_SPEC.md`](./CONTROL_PLANE_SPEC.md) §6–§11, [`ROADMAP.md`](./ROADMAP.md), ADR-003  
**Constraint:** All workstreams must obey the [Six Architecture Principles](./ARCHITECTURE.md).

## Goal

Extend Mintry from single-agent local governance to multi-agent fleets and language-agnostic enforcement — without putting network I/O or non-deterministic logic on the hot path.

## Architecture target (Option A fleet)

```text
Author (Dashboard)
        │  org tree OR fleet_total + partitions
        │  compile inheritance → flat agent caps
        │  validate sum(shares) ≤ total
        │  for each agent: canonical ES256 sign → INSERT policy_bundles
        ▼
   Supabase control plane (immutable versions per agent)
        │  each agent polls its own agent_id (async)
        │  sync-time: materialize OPA/nested envelopes → flat rules
        ▼
   PolicyCache (verified local max_usd)
        │  synchronous local read only
        ▼
   PolicyEngine.authorize() / mintry-proxy  ←── no fleet / Redis / OPA CLI
```

## Workstream map

| ID | Workstream | Status |
| --- | --- | --- |
| **E0** | Fleet Option A authoring + validation | **Done** |
| **E1** | Agent-grouped ledger (UI) | **Done** |
| **E2** | Org / project hierarchy (compile → flat caps) | **Done** |
| **E3** | Go sidecar scaffold (ADR-003) | **Done** (HTTPS MITM follow-up) |
| **E4** | OPA bundle compile-at-sync | **Done** |
| **E5** | Vault alias orchestration | **Done** |

## E0 — Fleet Option A

See earlier deliverables: `mintry.core.fleet`, `POST /api/fleets/partition`, dashboard Fleet Partition panel.

## E1 — Agent-grouped ledger

Dashboard groups mandates by agent with rollup budget/spent/policy version.

## E2 — Org hierarchy

- `mintry.core.org.compile_org_to_agent_caps` — Company → department → project → agent
- Inheritance resolves at author time into flat `agent_id → max_usd`
- `POST /api/orgs/compile` (+ optional fleet push)
- Dashboard **Org Hierarchy Compile** panel

## E3 — Go sidecar

- `apps/sidecar` / `mintry-proxy` on `:8820`
- Local SQLite authorize + meter + intent blocklist
- Alpine Dockerfile, compose, `deploy/k8s-sidecar.yaml`
- HTTPS CONNECT MITM remains a follow-up (`501` unless uninspected tunnel)

## E4 — OPA compile-at-sync (eval outcome)

**Decision:** Keep the custom budget evaluator on the hot path. Use OPA-shaped bundles only as a **distribution envelope**. At policy apply/sync time, `materialize_flat_rules()` unwraps nested/OPA maps into flat `{max_usd, allow, expires_at}` for `PolicyCache`. The OPA CLI is **never** spawned from authorize.

## E5 — Vault alias orchestration

- `mintry.core.secrets` — alias validation + resolve from customer env / optional customer Vault agent
- `POST /api/secrets/aliases` — accepts alias references only; rejects raw key payloads
- Mintry servers never store provider API keys

## Follow-ups (not blocking Phase 2 gate)

- Sidecar TLS MITM for HTTPS LLM hosts
- Sidecar built-in policy poller (today: Python SDK sync)
- Option B Redis global hard cap (only if Option A insufficient)
