# Mintry Fabric — Control Plane / Data Plane Architecture Spec

**Status:** Implemented through Phase 2 (`v1.1.1`) — living spec  
**Owner:** Zolile Nonzapa  
**Purpose:** Single source of truth for how Mintry's dashboard, SDK, and sidecar fit together.  
**Companion docs:** [ARCHITECTURE.md](./ARCHITECTURE.md), [PHASE2_PLAN.md](./PHASE2_PLAN.md), [ROADMAP.md](./ROADMAP.md)

## Recorded Decisions

| Section | Decision | Status |
| ------- | -------- | ------ |
| §4.3 OPA bundles | OPA-shaped envelopes for distribution; **materialize flat rules at sync**; custom evaluator for budget math; **never spawn OPA CLI on authorize** | **Decided — implemented (E4)** |
| §6 Fleet budget | Option A — static sub-budget partitioning | **Approved — implemented (E0)** |
| §7 Secrets | Alias references only; resolve on customer host (env / Vault agent); never store provider keys on Mintry | **Approved — implemented (E5)** |
| §8 Scope guardrails | Routing and anomaly/recommendation remain out of scope | **Approved** |
| §3.2 Turso | Skip Turso; local SQLite + batched POST to Supabase | **Approved** |
| §9 Authoring | With control plane configured, local SQLite upsert/revoke requires `MINTRY_LOCAL_GOVERNANCE=1`; **Sign & Push is source of truth** | **Approved — implemented (v1.1.1)** |

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
   │  Dashboard (Next.js)     Auth (admin token today; Supabase Auth │
   │  Sign & Push / Fleet     UI next)                               │
   │  Org compile → caps      Policy Validator / ES256 Signer        │
   │  Telemetry ingest        Alias-only secret refs (no raw keys)   │
   └─────────────────────────────────────────────────────────────────┘
                      │  policy_bundles (signed, versioned)  │  telemetry (async, batched)
                      ▼                                      ▲
                         DATA PLANE  (customer infrastructure)
   ┌─────────────────────────────────────────────────────────────────┐
   │  Python SDK (supported)  /  Go mintry-proxy (scaffold)            │
   │  PolicyCache (verified LKG) + sync-time flat rule materialize     │
   │  Local SQLite WAL ledger (spend-to-date, independent of policy)   │
   │  PolicyEngine.authorize() — local, sync, zero CP network I/O      │
   │  Kill switch / intent blocklist                                   │
   └─────────────────────────────────────────────────────────────────┘
```

**CTO pitch:** If our cloud disappears, production agents keep enforcing the last verified policy.

**Supported path today:** Python SDK + dashboard Sign & Push (and Fleet/Org compile → Sign & Push).  
**Scaffold:** `apps/sidecar` (`mintry-proxy`) — HTTP metering; HTTPS MITM not done.  
**Not the control plane:** legacy `apps/sync-api` Express stub.

---

## 3. Deployment Architecture

### 3.1 Control Plane

| Layer | Choice | Notes |
| ----- | ------ | ----- |
| Frontend + API routes | Vercel / Next.js | Sign, fleet partition, org compile, alias validate |
| Auth + relational data | Supabase | `policy_bundles`; admin token / login cookie today |
| Ledger sync / telemetry | Supabase | Batched POST from SDK; Turso Sync deferred |

### 3.2 Turso — Deferred (Approved)

Skip Turso for early users. Local SQLite + batched POST to Supabase keeps zero-latency hot path with one fewer vendor.

When Turso is introduced, specify **Turso Sync / offline mode** — not classic libSQL Embedded Replicas (writes forward synchronously to remote primary).

### 3.3 Interceptor Distribution

| Phase | Package | Distribution | Maturity |
| ----- | ------- | ------------ | -------- |
| Phase 1 | Python SDK | `pip` / git install | **Supported** |
| Phase 2 | Go `mintry-proxy` | Alpine Docker / k8s sidecar | **Scaffold** (HTTPS MITM follow-up) |
| — | `packages/mintry-node` | private `0.1.0` | **Prototype** |

---

## 4. Policy Model

### 4.1 Policy as versioned, signed, immutable record

Every change creates a new version in `policy_bundles`. Never edit in place.

Canonical ES256 contract (dashboard sign ↔ Python verify):

- Fields: `version`, `mandates`, `issued_at`, `issued_by`
- Bytes: JSON with sorted keys, compact separators, UTF-8
- Alg: ES256 (ECDSA P-256 + SHA-256), signature base64

### 4.2 Rollback semantics

Rolling back policy changes **future enforcement only**. The spend ledger is independent — rollback never rewrites historical spend.

Example: Agent spends $220 under v18 ($250 cap). Rollback to v17 ($500 cap) → remaining = $500 − $220 = $280, not a fresh $500.

### 4.3 Policy pipeline

```
Dashboard (Sign & Push | Fleet | Org compile)
        → validate → (optional OPA-shaped envelope)
        → materialize intent as flat mandate rules
        → canonical ES256 sign → INSERT policy_bundles
        → agent poll (15–30s) → verify → PolicyCache atomic swap
        → authorize hot path reads flat rules only
```

### 4.4 OPA eval outcome (E4)

| Keep | Drop from hot path |
| ---- | ------------------ |
| Custom budget math in `PolicyEngine.authorize()` | Spawning `opa` CLI per request |
| OPA-shaped / nested bundles as **distribution envelopes** | Non-deterministic policy logic |

At sync/apply time, `materialize_flat_rules()` unwraps envelopes into
`mandate_id → {max_usd, allow, expires_at}` for `PolicyCache`.

---

## 5. Local Evaluation & Fail-Safe Behavior

### 5.1 Hot path (never touches network)

`LLM Request → PolicyCache / ledger → Evaluate → Allow/Block → Meter → Continue`

### 5.2 Sync loop

- Poll every 15–30 seconds (Python `PolicySyncWorker`)
- Compare monotonic version number
- Atomic ruleset swap + disk LKG
- Startup: never refuse to start when control plane unreachable; use last cached policy

### 5.3 Signature verification

Reject unsigned/invalid policy payloads when a public key is configured; continue enforcing last valid policy; log auditable event.

### 5.4 Staleness visibility

Dashboard shows last-synced timestamp, applied policy version, and `control_plane_healthy` per summary poll.

Emergency Stop is a command, not a cached value — partitioned sidecars keep last-synced state until connectivity returns.

---

## 6. Fleet-Wide Budget Consistency

**Decision: Option A — static sub-budget partitioning** (implemented).

Authors set `fleet_total` + `{agent_id → share}` with `sum(shares) ≤ total`.
Each agent receives a signed policy whose local `max_usd` is its share.
No shared Redis counter on the hot path.

Revisit **Option B** (Redis/Upstash atomic counter) only when a true global hard cap is required across pods beyond Option A.

Surfaces: `mintry.core.fleet`, `POST /api/fleets/partition`, dashboard Fleet Partition panel.

---

## 7. Secrets Handling

Mintry never stores customer provider API keys.

- Dashboard accepts **alias references only** (e.g. `OPENAI_PROD_KEY`) via `POST /api/secrets/aliases`
- Raw `value` / `api_key` fields are rejected
- SDK resolves aliases from customer environment or optional customer Vault agent (`mintry.core.secrets`)
- Never contacts the Mintry control plane to fetch secret material

---

## 8. Scope Guardrails (Deferred)

| Feature | Status |
| ------- | ------ |
| Automatic model rerouting | **Deferred** — conflicts with runtime financial governance positioning |
| Anomaly/recommendation engine | **Deferred** — non-deterministic; belongs in analytics layer |
| Push-based policy propagation (WebSocket/SSE) | **Deferred** — polling is the stated contract until enterprise SLA requires push |

---

## 9. Data Model & Authoring

### 9.1 Agent as primary object

Agent is primary; Mandate is a property. Dashboard groups ledger rows by agent (E1).

### 9.2 Organization hierarchy

Company → department → project → agent budget inheritance.

Inheritance **compiles at author time** into flat `agent_id → max_usd` (`mintry.core.org`, `POST /api/orgs/compile`). The hot path never walks the tree.

### 9.3 Authoring modes (v1.1.1)

| Condition | Local SQLite upsert/revoke | Source of truth for caps |
| --------- | -------------------------- | ------------------------ |
| No `MINTRY_CONTROL_PLANE_URL` | Allowed | Local ledger (air-gapped) |
| Control plane configured | **Denied** unless `MINTRY_LOCAL_GOVERNANCE=1` | Signed `policy_bundles` via Sign & Push |
| Hybrid opt-in | Allowed when flag set | Prefer Sign & Push; local edits are explicit |

Summary API exposes `governance.authoring_mode`:
`central_sign_and_push` | `hybrid_local_opt_in` | `local_ledger`.

---

## 10. Dashboard Credibility (§10)

All complete (Phase 1):

1. [x] Hide integration-test data in prospect environments (`MINTRY_DEMO_MODE`)
2. [x] Hide Expiry column until meaningful (`has_expiry`)
3. [x] Brand palette (#050505 / #10B981)
4. [x] Live Audit Feed: ALLOW / BLOCK / SPEND above the fold
5. [x] KPIs: Protected Spend / Requests Blocked / Overspend Prevented

Additional (v1.1.1): Sign & Push / Fleet / Org lead the admin column; local ledger edits demoted and gated.

---

## 11. Phased Roadmap

### Phase 1 — Alpha (`v1.0.0`) — complete

- [x] Python SDK, local SQLite ledger
- [x] Vercel + Supabase control plane (skip Turso)
- [x] Polling policy sync, version number, atomic swap, last-known-good cache
- [x] Signature verification on policy payloads
- [x] Dashboard fixes §10
- [x] Agent-grouped ledger view (UI) — landed with Phase 2 E1
- [x] Rollback semantics (ledger independent of policy version)
- [x] Admin token auth; production readiness DoD

### Phase 2 — Enterprise (`v1.1.0` / `v1.1.1`) — complete

- [x] Go sidecar scaffold (`apps/sidecar` / `mintry-proxy`; HTTPS MITM follow-up)
- [x] Option A fleet budget partitioning
- [x] Agent-grouped ledger (UI)
- [x] Org/project hierarchy compile → flat caps
- [x] OPA compile-at-sync materialization (E4 outcome above)
- [x] Secrets alias-only orchestration
- [x] Promise alignment: central authoring default when CP configured

### Next (see [ROADMAP.md](./ROADMAP.md))

1. Sidecar HTTPS MITM
2. Sidecar built-in policy poller (verify → LKG → flat caps)
3. Full Supabase Auth UI
4. Configurable intent blocklists in signed policy
5. Option B fleet hard cap (only if Option A insufficient)

### Deferred (§8)

- Routing, ML recommendations
- Push-based policy propagation
