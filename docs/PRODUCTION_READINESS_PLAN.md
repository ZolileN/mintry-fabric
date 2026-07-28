# Production Readiness Plan — Tighten the Bolts

**Status:** Phase 1 DoD met — shipped as `v1.0.0`  
**Source:** [`APP_ANALYSIS.md`](./APP_ANALYSIS.md) gaps + [`CONTROL_PLANE_SPEC.md`](./CONTROL_PLANE_SPEC.md) + Six Principles  
**Goal:** Close the control-plane → enforce loop and ship a credible production `v1.0.0` for Phase 1 (Python SDK + Vercel/Supabase dashboard).

This is an implementation plan, not a calendar estimate. Work is ordered by **architectural leverage** and **dependency**. Each workstream lists concrete deliverables, file targets, acceptance criteria, and principle constraints.

---

## Definition of Done (production-ready Phase 1)

Ship only when **all** of the following are true:

1. **Closed enforce loop.** A signed central policy changes allow/block on the interceptor within one poll interval, with zero network I/O on the hot path.
2. **Crypto contract.** Dashboard sign and Python verify use identical canonical bytes; unsigned/invalid bundles are rejected when keys are configured; last-known-good continues to enforce.
3. **Auth boundary.** Dashboard mutations and policy publish require authenticated control-plane identity; Python data API is not world-writable.
4. **Ledger integrity.** Concurrent requests cannot silently overspend past configured caps under documented concurrency assumptions; audit log remains append-only for spend history.
5. **Honest product surface.** Legacy stubs (`sync-api`) and unfinished peers (`mintry-node`) are labeled and cannot be mistaken for production control plane / peer SDK.
6. **Proof.** Automated tests cover (1)–(3); docs and ROADMAP match the live topology.

**Out of scope for this plan (stay deferred):** sidecar, fleet Redis caps, push sync, model rerouting, anomaly ML, multi-tenant org hierarchy beyond basic agent_id.

---

## Architecture target (must match code)

```text
Author (Dashboard, authenticated)
        │  validate → canonical ES256 sign → INSERT policy_bundles (immutable)
        ▼
   Supabase control plane
        │  async poll 15–30s (urllib, not httpx)
        ▼
   PolicyCache (verified, atomic swap, disk LKG)
        │  synchronous local read only
        ▼
   PolicyEngine.authorize()  ←── interceptor hot path
        │  allow / block / configured number
        ▼
   Wallet spend (SQLite WAL) + append-only audit
        │  async batched telemetry (optional)
        ▼
   Control plane ingest
```

**Hard rule:** Nothing in the interceptor may call HTTP/RPC/OPA CLI. OPA (if kept) stays off the hot path or becomes a precompiled in-memory rule set applied at sync time.

---

## Workstream map

| ID | Workstream | Depends on | Risk if skipped |
| --- | --- | --- | --- |
| **P0** | Crypto + env contract | — | Signed policies never verify |
| **P1** | Close enforce loop | P0 | Central governance is theater |
| **P2** | Auth + API hard boundary | — | Any reachable admin is RCE-for-budgets |
| **P3** | Ledger concurrency + durability | P1 | Overspend under load |
| **P4** | Dashboard credibility + sync UX | P1, P2 | Demo looks broken / stale |
| **P5** | Telemetry path live | P1 | Control plane blind to spend |
| **P6** | Quarantine legacy / Node honesty | — | Wrong topology in ops |
| **P7** | Docs, versioning, release gate | All | False “1.0.0” claim |

Recommended merge order: **P0 → P1 → P2** in parallel with **P6**; then **P3 + P5**; then **P4**; finish with **P7**.

---

## P0 — Single crypto and config contract

### Problem

Next signs with `JSON.stringify` + `MINTRY_PRIVATE_KEY` (or mock). Python verifies canonical sorted JSON + `MINTRY_POLICY_PUBLIC_KEY`. Names and bytes disagree.

### Deliverables

1. **Canonical payload spec** (document + shared test vectors):
   - Fields: `version`, `mandates`, `issued_at`, `issued_by`
   - Bytes: `json.dumps(..., separators=(",", ":"), sort_keys=True)` UTF-8
   - Alg: ES256 (ECDSA P-256 + SHA-256), signature base64
2. **Dashboard signer** (`apps/dashboard/src/app/api/policies/sign/route.ts`):
   - Use canonical serialization (port Python rules or call a tiny shared fixture)
   - Read `MINTRY_POLICY_PRIVATE_KEY` (keep temporary alias for `MINTRY_PRIVATE_KEY` with warning log)
   - **Fail closed** when private key missing in `NODE_ENV=production` / `MINTRY_REQUIRE_POLICY_SIGNATURES=1`
   - Remove success path for `mock_signature_for_phase2_spike` outside explicit `MINTRY_ALLOW_MOCK_SIGNATURES=1` (dev only)
3. **Python verify always on when key present** (`src/mintry/__init__.py`, `core/crypto.py`):
   - Load `MINTRY_POLICY_PUBLIC_KEY` from env if `control_plane_public_key` omitted
   - Re-verify disk LKG on load; discard invalid cache and keep memory empty / prior valid
4. **Contract tests:**
   - Python signs → Python verifies
   - Fixture signed like Next → Python verifies
   - Tampered mandate / version → reject; LKG unchanged

### Acceptance

- [x] One env naming scheme in `.env.example`, `SUPABASE_SETUP.md`, dashboard, and `init()`
- [x] CI test proves Next-shaped canonical bytes verify in Python
- [x] Production config without keys cannot publish “signed” policies

### Principle check

- §2 Author as versioned fact (real signatures)
- §5 Reject invalid; keep LKG

---

## P1 — Close the enforce loop

### Problem

Interceptor → `PolicyEngine.authorize()` → wallet only.  
`PolicyCache` + `check_authorization()` (OPA) are disconnected from the hot path.

### Design (preferred)

Keep **one** authorization entrypoint: `PolicyEngine.authorize()`.

On each request (sync, local only):

1. Resolve `mandate_id` (header / future context — keep header for now).
2. Read **active verified policy** from `PolicyCache.get_active_policy()` if present.
3. Resolve **configured cap** for that mandate:
   - If policy contains the mandate → use policy `max_usd` (and expiry if present in bundle).
   - Else → fall back to local wallet mandate row (local/dev mode).
4. Compare against **local spent_usd** from wallet cache (ledger stays source of spend truth).
5. Apply deterministic rules only: expired → block; exhausted → block; remaining &lt; safety headroom → block; optional intent blocklist from **policy bundle** when present else built-in.
6. Never call network / OPA CLI here.

**OPA:** For Phase 1 production, treat OPA as optional compile-time / sync-time validator, not hot-path. If in-process OPA can evaluate in &lt;1ms against cached data without spawning a process, it may run at sync apply time to materialize a flat `mandate_id → {max_usd, expires_at, allow}` map into `PolicyCache`. Do **not** spawn `opa` CLI per request.

### Local vs central mutations

| Mode | Mandate upsert/revoke | Who is source of truth |
| --- | --- | --- |
| **Production** | Dashboard “Sign & Push” only; local Python upsert disabled or requires `MINTRY_LOCAL_GOVERNANCE=1` | Signed policy versions |
| **Local/dev** | Python `/api/mandates/*` allowed; clearly labeled | Local SQLite |

Production dashboard allocate/revoke should **update the next policy version** (central author), not silently PATCH SQLite on a remote agent. Agents apply caps on next successful poll. Spend ledger remains local and independent (rollback semantics §4.2).

### File targets

- `src/mintry/core/engine.py` — authorize reads PolicyCache caps
- `src/mintry/interceptors/global_http.py` — keep calling authorize only; add zero-network assertion hooks in tests
- `src/mintry/core/policy_sync.py` — materialize flat mandate map at apply; agent/db-scoped cache path
- `src/mintry/core/wallet.py` — deprecate hot-path use of `check_authorization`; keep as legacy wrapper
- `src/mintry/core/dashboard.py` — gate local mutations; pass public key into `init()`
- `tests/` — new E2E: sign → cache apply → intercept block/allow

### Acceptance

- [x] E2E test: policy vN cap $1.00 with $0.99 spent → next LLM call blocked without hitting control plane
- [x] E2E test: unreachable control plane → LKG still enforces previous cap
- [x] E2E test: invalid signature → cache not swapped; audit/log event recorded
- [x] Test spy: interceptor path makes zero outbound sockets to control plane
- [x] Repeated `init()` is idempotent (same engine/interceptor; no dual wallets)

### Principle check

- §1 Init once / governance without code changes
- §3 Enforce locally
- §4 Async sync
- §5 LKG
- §6 Deterministic numbers only

---

## P2 — Auth and hard API boundary

### Problem

All dashboard and Python admin routes are open. Service-role key behind unauthenticated Next routes.

### Deliverables

1. **Dashboard auth (Supabase Auth)** — matches CONTROL_PLANE_SPEC:
   - Middleware / layout guard for UI
   - API routes require valid session (or service JWT) before proxy/sign
   - Map authenticated user → allowed `agent_id` / org (start with allowlist env or `profiles` table; full org hierarchy stays Phase 2)
2. **Separate keys:**
   - Browser never sees service role
   - Sign route uses server-only service role **after** authz check
   - Anon/authenticated client for user reads where possible
3. **Python dashboard API:**
   - Default bind `127.0.0.1`
   - Require `MINTRY_DASHBOARD_API_TOKEN` (Bearer) for mutating routes when not loopback-only mode
   - Tighten CORS: echo configured `MINTRY_DASHBOARD_UI_ORIGIN`, not `*`
4. **sync-api:** do not add auth theater — quarantine (P6) instead of “securing” a dead path

### Acceptance

- [x] Unauthenticated `POST /api/policies/sign` → 401 *(when `MINTRY_REQUIRE_AUTH=1` / production + admin token)*
- [x] Unauthenticated mandate upsert/revoke via Next → 401 *(same gate)*
- [x] Python mutate without token (when required) → 401
- [x] SECURITY.md and DEPLOYMENT.md updated

### Principle check

- Does not put auth on the LLM hot path (auth is control-plane / admin only)

---

## P3 — Ledger concurrency and durability

### Problem

Pre-flight uses flat `$0.01` headroom; metering is post-flight async → concurrent overshoot. Writer errors can drop queued persists.

### Deliverables

1. **Per-mandate lock** around authorize + spend reservation in the in-memory wallet.
2. **Reserve / settle model (recommended):**
   - Pre-flight: reserve `min(estimate, remaining)` or a configurable default estimate from pricing registry when body parses; else conservative default
   - Post-flight: settle actual cost; release unused reservation
   - On upstream failure: release reservation
3. **Writer reliability:**
   - Failures re-queue or crash-process loudly (never mark complete after silent discard)
   - `atexit` / explicit `engine.close()` flushes queue
4. **Monetary type:** migrate hot budget math toward `Decimal` quantized to 4 dp (ledger column migration carefully; don’t rewrite historical audit amounts).
5. **Stress tests:** N concurrent intercepts against $1.00 cap never exceed cap + one in-flight estimate (document bound).

### Acceptance

- [x] Concurrent test cannot spend past cap beyond documented reservation bound
- [x] Process shutdown flushes pending writes in tests
- [x] No silent drop of wallet write tasks *(failed batches are re-queued)*

### Principle check

- §6 Deterministic configured numbers
- Ledger history not rewritten on policy rollback

---

## P4 — Dashboard credibility and sync UX

Aligns with CONTROL_PLANE_SPEC §10, plus analysis bugs.

### Deliverables

1. Fix `has_expiry` hard-coded `False` in `dashboard.py`; hide column in UI when false.
2. Cumulative spend chart from mandate totals / full spend series, not only last 100 audit rows (or label chart “Recent activity”).
3. Per-mandate policy version + last sync: show process-level sync once in header; don’t pretend each row has distinct sync time unless agent-scoped data exists.
4. Reduce summary cost:
   - Stop full-table `policy_bundles` scan every 3s — query latest per `agent_id` or cache briefly
   - Move control-plane health check off the request path (background) or cache 30s
   - Client poll interval configurable (default 5–10s)
5. §10 UI: hide test mandates in demo mode (already partial); brand palette; ALLOW/BLOCK prominence; KPI names.
6. Production allocate/revoke UX: “Sign & Push” as primary; local-only controls behind advanced/dev flag.

### Acceptance

- [x] Prospect demo shows no integration-test mandate ids when `MINTRY_DEMO_MODE=1`
- [x] Expiry column hidden unless real expiries exist
- [x] First load without control plane does not block ~7s on every refresh (cached health)

---

## P5 — Telemetry path live

### Problem

`TelemetryBatcher` exists and is tested but not started from `init()`.

### Deliverables

1. Construct and start batcher from `init()` when control plane configured.
2. Idempotent event ids on spend/block posts (prevent double-count on retry).
3. Never block interceptor on telemetry failure (async only).
4. Document env: batch size, flush interval, disable flag.

### Acceptance

- [x] Integration test: spend → batcher queue → mock control plane receives events
- [x] Control plane down → enforcement unaffected; errors visible in sync/telemetry status

---

## P6 — Quarantine legacy and honest Node package

### Deliverables

1. **`apps/sync-api`:**
   - README banner: LEGACY / DEMO ONLY — not production control plane
   - Remove or demote from `DEPLOYMENT.md` primary path
   - Optional: `package.json` `"private": true` and rename scripts to `demo:*`
2. **`packages/mintry-node`:**
   - Version → `0.1.0` (or `0.x`) until build + policy sync exist
   - Fix `main`/`exports`/build or mark `"private": true`
   - README: experimental; Python is supported enforcement SDK
   - Do not claim parity in RELEASE_NOTES
3. Stop committing new guidance that treats sync-api as live control plane.

### Acceptance

- [x] New contributor reading DEPLOYMENT + ARCHITECTURE gets one topology
- [x] Node package cannot be `npm install`ed as a broken `1.0.0` main entry without warning

---

## P7 — Docs, versioning, release gate

### Deliverables

1. Update `ROADMAP.md` Phase 1 checkboxes to match reality (partial code vs done).
2. Fix `SECURITY.md` (e.g. `MINTRY_API_KEY` auto-read claim vs code).
3. Replace dashboard create-next-app README.
4. Align `__version__` / CHANGELOG: either stay pre-1.0 until DoD met, or publish `1.0.0` only after this plan’s gate.
5. **Release checklist** (must pass CI):
   - Full pytest (document known free-threaded flakes separately)
   - Crypto contract tests
   - Enforce-loop E2E
   - Auth route tests
   - Dashboard lint (fix known `any` in summary route)
   - Manual: localhost demo script in `RUN_LOCAL.md`

### Suggested versioning

| Milestone | Version signal |
| --- | --- |
| After P0+P1+P2 merge | `0.6.0` — control plane alpha that actually enforces |
| After P3+P4+P5 | `0.7.0` — hardening |
| After P6+P7 + DoD | `1.0.0` — production Phase 1 |

---

## Test matrix (minimum new coverage)

| ID | Test | Workstream |
| --- | --- | --- |
| T1 | Canonical sign/verify interop fixture | P0 |
| T2 | Reject unsigned when key configured | P0 |
| T3 | Policy apply changes intercept allow/block | P1 |
| T4 | Invalid policy keeps LKG enforcement | P1 |
| T5 | Interceptor makes zero CP network calls | P1 |
| T6 | Dashboard API 401 without session | P2 |
| T7 | Concurrent spend respects cap bound | P3 |
| T8 | Wallet flush on close | P3 |
| T9 | Telemetry batch from init | P5 |

---

## Implementation sequence (PR slices)

Prefer small PRs that each leave `main` green:

1. **PR-A (P0):** Crypto canonicalization + env rename + contract tests (no behavior change to authorize yet).
2. **PR-B (P1):** PolicyCache → authorize wiring + E2E enforce tests + idempotent init.
3. **PR-C (P2):** Supabase auth middleware + Python API token + CORS.
4. **PR-D (P6):** Docs quarantine sync-api / Node demotion (can land anytime after A).
5. **PR-E (P3):** Reservation + writer flush + concurrency tests.
6. **PR-F (P5):** Wire TelemetryBatcher.
7. **PR-G (P4):** Dashboard credibility + summary performance.
8. **PR-H (P7):** Roadmap/SECURITY/version bump to 1.0.0 when DoD met.

Do not combine auth + enforce-loop + crypto in one PR unless necessary — reviewability matters for money-path code.

---

## Explicit refusals (architecture)

These must **not** appear in “production ready” shortcuts:

- Network call inside interceptor “to be sure” the policy is fresh
- Fail-open when cache missing in production (fail to LKG or fail closed with explicit config — never silent allow)
- In-place edit of `policy_bundles` rows
- Rewriting historical spend on policy rollback
- Using OPA CLI with multi-second timeout on the hot path
- Shipping mock signatures in production configs

---

## Tracking

- Gap inventory: [`APP_ANALYSIS.md`](./APP_ANALYSIS.md)
- Normative architecture: [`ARCHITECTURE.md`](./ARCHITECTURE.md), [`CONTROL_PLANE_SPEC.md`](./CONTROL_PLANE_SPEC.md)
- Progress: check boxes in this doc per merged PR; mirror summary into `ROADMAP.md` Phase 1

When a workstream completes, update APP_ANALYSIS §7/§8 so the next analysis checkpoint is mechanical, not aspirational.
