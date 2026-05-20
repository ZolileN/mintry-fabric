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
