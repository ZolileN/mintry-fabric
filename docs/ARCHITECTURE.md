# Mintry Fabric Architecture Map

Mintry Fabric utilizes a decoupled architecture that separates the control and enforcement planes. This ensures that the enforcement plane (the logic fabric that meters spend and blocks intents) runs on the customer's infrastructure with zero latency, while the control plane syncs state asynchronously.

## Deployment Topology

| Component | What it Runs | Where it Lives | Cost to You |
| --------- | ------------ | -------------- | ----------- |
| **Frontend** | Next.js Marketing & Dashboard | Vercel | $0 (Free Tier) |
| **Control Plane** | Central Sync API & Sync Database | Render | $0 to $5/mo |
| **Enforcement Plane** | Core Logic Fabric + Local SQLite Ledger | Customer's Infrastructure | $0 (Paid by client) |

## Component Breakdown

### 1. Frontend (Vercel)
The user-facing Next.js application serves dual purposes:
- The marketing website outlining the value proposition.
- The web dashboard where administrators can view global spend, configure policies, and allocate budgets.

### 2. Control Plane (Render)
The centralized Sync API acts as the bridge between the customer environments and the central dashboard. It provides asynchronous syncing of local SQLite WAL logs up to the central Postgres/cloud database.

### 3. Enforcement Plane (Customer's Infrastructure)
The actual budget enforcement, monkey-patching, and sidecar proxy interception run directly on the client's servers. 
- Using the Python/Node SDKs or the Sidecar Proxy.
- Writes to the local SQLite `vouchers.db` for zero-latency authorization.
- Zero network hops are added to the LLM critical path for fiscal and intent checks.

## The Six Architecture Principles

These govern every future feature decision. Before building anything, run it against these:

1. **Initialize once.** A developer integrates Mintry a single time (`mintry.init()`). No further code changes are required for any governance change.
2. **Author centrally, as versioned fact.** Every policy change is an immutable, attributed, timestamped record — never an in-place mutation. Rollback changes future enforcement only; it never rewrites the historical ledger of what was actually spent.
3. **Enforce locally, always.** Every runtime decision (allow/block) evaluates synchronously against the last verified local policy. No request's latency depends on the Mintry control plane being reachable.
4. **Sync asynchronously, on a stated interval, with visible staleness.** Policy propagation is polling-based and honestly described ("within 30 seconds"), not oversold as instant — until a specific enterprise requirement justifies the cost of push infrastructure. Every agent's dashboard entry shows last-synced timestamp and policy version.
5. **Fail to last-known-good, never open, never silently closed.** Unreachable control plane → keep enforcing the last signed policy. Invalid/unsigned policy payload → reject it, keep enforcing the last valid one. Either way: a loggable, auditable event.
6. **Stay deterministic.** If a feature can't be expressed as "allow, block, or a number the customer configured," it does not belong in the enforcement path. It belongs in a separate, clearly labeled analytics layer — or on someone else's roadmap.
