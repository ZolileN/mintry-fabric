# Mintry Fabric — Control Plane / Data Plane Architecture Spec

**Status:** Ready for implementation  
**Owner:** Zolile Nonzapa  
**Purpose:** Single source of truth for how Mintry's dashboard, SDK, and sidecar fit together.

## Recorded Decisions

| Section | Decision | Status |
| ------- | -------- | ------ |
| §4.3 OPA bundles | Evaluate OPA bundle mechanism for policy distribution/signing; keep custom evaluator for budget math until eval completes | **Approved — evaluate first** |
| §6 Fleet budget | Option A — static sub-budget partitioning for Phase 1/early Phase 2 | **Approved** |
| §8 Scope guardrails | Routing and anomaly/recommendation features remain explicitly out of scope | **Approved** |
| §3.2 Turso | Phase 1 skips Turso; local SQLite ledger + batched POST to Vercel/Supabase for telemetry | **Approved** |

---

## 1. The Six Architecture Principles

These govern every future feature decision. See [ARCHITECTURE.md](./ARCHITECTURE.md).

1. **Initialize once.** `mintry.init()` — no further code changes for governance changes.
2. **Author centrally, as versioned fact.** Immutable, attributed, timestamped policy records.
3. **Enforce locally, always.** Synchronous evaluation against last verified local policy.
4. **Sync asynchronously, on a stated interval, with visible staleness.** Polling-based; show last-synced + policy version per agent.
5. **Fail to last-known-good, never open, never silently closed.**
6. **Stay deterministic.** Allow, block, or a configured number — nothing else in the enforcement path.

---

## 2. System Architecture

```
                        CONTROL PLANE  (Vercel + Supabase)
   ┌─────────────────────────────────────────────────────────────────┐
   │  Dashboard (Next.js)     Auth (Supabase)     Billing (Stitch)    │
   │  Policy Editor           Policy Validator/Signer                 │
   │  Telemetry Ingest        Audit Log Store                         │
   └─────────────────────────────────────────────────────────────────┘
                      │  policy bundle (signed, versioned)  │  telemetry (async, batched)
                      ▼                                     ▲
                         DATA PLANE  (customer infrastructure)
   ┌─────────────────────────────────────────────────────────────────┐
   │  Python SDK (Phase 1)  /  Go-Rust Sidecar (Phase 2)               │
   │  Local policy cache (last-known-good)                             │
   │  Local SQLite WAL ledger (spend-to-date, independent of policy)   │
   │  Policy evaluator (local, synchronous, zero network calls)        │
   │  Kill switch                                                      │
   └─────────────────────────────────────────────────────────────────┘
```

**CTO pitch:** If our cloud disappears, production agents keep enforcing the last verified policy.

---

## 3. Deployment Architecture

### 3.1 Control Plane

| Layer | Choice | Notes |
| ----- | ------ | ----- |
| Frontend + API routes | Vercel | Next.js dashboard, serverless webhooks |
| Auth + relational data | Supabase | Profiles, billing tiers, mandate/policy configs |
| Ledger sync / telemetry | Supabase (Phase 1) | Batched POST from SDK; Turso Sync deferred |

### 3.2 Turso — Phase 1 Alternative (Approved)

Skip Turso for the first 5–10 users. Local SQLite + batched POST to Supabase achieves zero-latency hot path with one fewer vendor.

When Turso is introduced, specify **Turso Sync / Turso Database with offline mode** — not classic libSQL Embedded Replicas (writes forward synchronously to remote primary).

### 3.3 Interceptor Distribution

| Phase | Package | Distribution |
| ----- | ------- | ------------ |
| Phase 1 — Alpha | Python SDK | `pip install mintry-fabric` (PyPI) |
| Phase 2 — Enterprise | Go/Rust sidecar | Alpine Docker → Docker Hub / ECR |

---

## 4. Policy Model

### 4.1 Policy as versioned, signed, immutable record

Every change creates a new version. Never edit in place.

### 4.2 Rollback semantics

Rolling back policy changes **future enforcement only**. The spend ledger is independent — rollback never rewrites historical spend.

Example: Agent spends $220 under v18 ($250 cap). Rollback to v17 ($500 cap) → remaining = $500 − $220 = $280, not a fresh $500.

### 4.3 Policy pipeline

Dashboard → Validator → Compiler → Signer → Distribution → SDK/Sidecar → Local memory → Runtime evaluation.

**OPA evaluation:** One-day eval of OPA bundle system for distribution/signing; custom lightweight evaluator retained for budget math until eval completes.

---

## 5. Local Evaluation & Fail-Safe Behavior

### 5.1 Hot path (never touches network)

`LLM Request → Policy in local memory → Evaluate → Allow/Block → Continue`

### 5.2 Sync loop

- Poll every 15–30 seconds
- Compare monotonic version number
- Atomic ruleset swap (tested module, not inline detail)
- Startup: never refuse to start when control plane unreachable; use last cached policy

### 5.3 Signature verification

Reject unsigned/invalid policy payloads; continue enforcing last valid policy; log auditable event.

### 5.4 Staleness visibility

Dashboard shows last-synced timestamp and applied policy version per agent.

Emergency Stop is a command, not a cached value — partitioned sidecars keep last-synced state until connectivity returns.

---

## 6. Fleet-Wide Budget Consistency

**Decision: Option A — static sub-budget partitioning** for Phase 1/early Phase 2.

Revisit Option B (Redis/Upstash atomic counter) when enterprise scale requires true global hard cap.

---

## 7. Secrets Handling

Mintry never stores customer provider API keys. SDK reads secrets from customer environment. Phase 3+: dashboard orchestrates alias references only (e.g. `OPENAI_PROD_KEY`).

---

## 8. Scope Guardrails (Deferred)

| Feature | Status |
| ------- | ------ |
| Automatic model rerouting | **Deferred** — conflicts with runtime financial governance positioning |
| Anomaly/recommendation engine | **Deferred** — non-deterministic; belongs in analytics layer |

---

## 9. Data Model

### 9.1 Agent as primary object

Agent is primary; Mandate is a property. UI-layer grouping first, deeper migration on its own timeline.

### 9.2 Organization hierarchy (Phase 2)

Company → department → project → agent budget inheritance.

---

## 10. Dashboard Fixes (Before New Features)

1. Remove integration-test data from prospect-visible environments
2. Hide Expiry column until meaningful
3. Collapse color system onto brand palette (#050505, #10B981 emerald, slate secondary)
4. Extend Live Audit Feed with ALLOW / BLOCK / THROTTLE; move above the fold
5. Reframe KPIs: Protected Spend / Requests Blocked / Overspend Prevented

---

## 11. Phased Roadmap

### Phase 1 — Alpha (current → next)

- [x] Python SDK, local SQLite ledger, .env auth
- [ ] Vercel + Supabase control plane (skip Turso)
- [ ] Polling policy sync, version number, atomic swap, last-known-good cache
- [ ] Signature verification on policy payloads
- [ ] Dashboard fixes §10
- [ ] Agent-grouped ledger view (UI layer)
- [ ] Rollback semantics (ledger independent of policy version)

### Phase 2 — Enterprise

- Go/Rust sidecar, K8s/ECS deployment
- Option A fleet budget partitioning
- Full Agent-as-primary data model
- Projects/org hierarchy
- OPA bundle eval outcome
- Secrets orchestration via customer Vault (alias-only)

### Phase 3 — Deferred

- Routing, ML recommendations (§8)
- Push-based policy propagation (WebSocket/SSE)
