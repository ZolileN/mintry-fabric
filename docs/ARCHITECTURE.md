# Mintry Fabric Architecture Map

Mintry Fabric utilizes a decoupled **control plane / data plane** architecture. The enforcement plane runs on customer infrastructure with zero added latency on the LLM hot path. The control plane authors and distributes signed policies asynchronously.

See [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md) for the full implementation spec.

## Deployment Topology

| Component | What it Runs | Where it Lives | Phase |
| --------- | ------------ | -------------- | ----- |
| **Frontend** | Next.js Dashboard | Vercel | 1 |
| **Control Plane** | Policy API, auth, telemetry ingest | Vercel + Supabase | 1 |
| **Enforcement Plane** | Python SDK + local SQLite ledger | Customer infrastructure | 1 |
| **Sidecar** | Go/Rust proxy daemon | Customer K8s/ECS | 2 |

**Phase 1 telemetry:** Local SQLite ledger + batched POST to Supabase. Turso Sync deferred until Postgres ingestion becomes the bottleneck.

## Component Breakdown

### 1. Frontend (Vercel)

Next.js dashboard for spend visibility, policy configuration, and budget allocation. Shows last-synced timestamp and policy version per agent.

### 2. Control Plane (Vercel + Supabase)

- Policy editor, validator, compiler, signer
- Signed policy bundle distribution
- Async telemetry ingest (never on enforcement hot path)
- Auth via Supabase

The legacy `apps/sync-api/` Express stub remains for local development; production targets Supabase.

### 3. Enforcement Plane (Customer Infrastructure)

- Python SDK (Phase 1) or sidecar proxy (Phase 2)
- Local policy cache with last-known-good fallback
- Local SQLite WAL ledger (spend-to-date, independent of policy version)
- Synchronous policy evaluator — **zero network calls on allow/block path**
- Kill switch

## The Six Architecture Principles

These govern every future feature decision. Before building anything, run it against these:

1. **Initialize once.** A developer integrates Mintry a single time (`mintry.init()`). No further code changes are required for any governance change.
2. **Author centrally, as versioned fact.** Every policy change is an immutable, attributed, timestamped record — never an in-place mutation. Rollback changes future enforcement only; it never rewrites the historical ledger of what was actually spent.
3. **Enforce locally, always.** Every runtime decision (allow/block) evaluates synchronously against the last verified local policy. No request's latency depends on the Mintry control plane being reachable.
4. **Sync asynchronously, on a stated interval, with visible staleness.** Policy propagation is polling-based and honestly described ("within 30 seconds"). Every agent's dashboard entry shows last-synced timestamp and policy version.
5. **Fail to last-known-good, never open, never silently closed.** Unreachable control plane → keep enforcing the last signed policy. Invalid/unsigned policy payload → reject it, keep enforcing the last valid one. Either way: a loggable, auditable event.
6. **Stay deterministic.** If a feature can't be expressed as "allow, block, or a number the customer configured," it does not belong in the enforcement path. It belongs in a separate, clearly labeled analytics layer — or on someone else's roadmap.
