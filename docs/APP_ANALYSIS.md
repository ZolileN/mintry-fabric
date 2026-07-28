# Mintry Fabric — Application Analysis

Snapshot of the applications and packages in this repository against the intended
control-plane / data-plane architecture (`docs/ARCHITECTURE.md`) and the Six
Architecture Principles.

**Scope:** `apps/dashboard`, `apps/sync-api`, `packages/mintry-node`, Python core
(`src/mintry`), plus supporting tools.

**Verdict:** Local enforcement and observability are real and useful for demos.
The control-plane loop (central author → sign → poll → verify → enforce) is
partially implemented and not yet closed end-to-end. Treat production claims
cautiously until the critical gaps below are closed.

---

## System map

```text
┌─────────────────────────────────────────────────────────────┐
│  Control plane (intended: Vercel + Supabase)                │
│  ┌──────────────────┐    ┌───────────────────────────────┐  │
│  │ apps/dashboard   │───▶│ Supabase policy_bundles       │  │
│  │ (Next.js BFF)    │    │ + telemetry ingest (planned)  │  │
│  └────────┬─────────┘    └───────────────▲───────────────┘  │
│           │ proxy                        │ poll (async)     │
└───────────┼──────────────────────────────┼──────────────────┘
            ▼                              │
┌───────────┴──────────────────────────────┴──────────────────┐
│  Enforcement / data plane (customer process)                │
│  ┌────────────────────┐  ┌────────────────────────────────┐ │
│  │ Python SDK         │  │ Local SQLite WAL ledger        │ │
│  │ httpx interception │──│ mandates + audit + policy rows │ │
│  │ + PolicyCache      │  └────────────────────────────────┘ │
│  └────────────────────┘                                     │
│  ┌────────────────────┐  ┌────────────────────────────────┐ │
│  │ mintry dashboard   │  │ packages/mintry-node (proto)   │ │
│  │ JSON API :8000     │  │ fetch patch + SQLite           │ │
│  └────────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Legacy (local/demo only): apps/sync-api Express JSON-file stub (:8080)
```

| Component | Path | Role | Maturity |
| --- | --- | --- | --- |
| Python SDK + CLI | `src/mintry` | Enforcement, ledger, local dashboard API | Primary product; strongest coverage |
| Dashboard UI | `apps/dashboard` | Observability + mandate/policy admin | Usable locally; not internet-safe |
| Sync API | `apps/sync-api` | Legacy telemetry/mandate stub | Demo-only; not the control plane |
| Node SDK | `packages/mintry-node` | Parallel enforcement SDK | Early prototype (version `1.0.0` overstates) |
| Gemini mock | `tools/gemini-mock-server` | Deterministic latency baseline | Tooling |
| k6 suites | `tools/k6` | Load / concurrency benchmarks | Tooling |

---

## 1. Python enforcement core (`src/mintry`)

### What it does well

- `mintry.init()` installs sync/async `httpx` hooks once; allow/block decisions
  run against local wallet state with **no control-plane call on the hot path**
  (Principles 3 and 6).
- Multi-provider metering (OpenAI, Anthropic, Gemini, Mistral) with a local
  pricing table.
- SQLite WAL ledger with in-memory cache, async writer, and append-oriented
  audit log.
- Policy sync scaffolding: `PolicyCache`, polling worker, disk last-known-good,
  ES256 helpers (`core/crypto.py`, `core/policy_sync.py`, `core/control_plane.py`).
- Local dashboard JSON API (`core/dashboard.py`) shares the same ledger as
  enforcement.
- Broad pytest suite (~100 tests) covering interception, pricing, wallet,
  CLI, dashboard allocate/revoke, and isolated policy/crypto clients.

### Critical gaps

1. **Synced policies are not on the enforcement path.**
   Interception calls `PolicyEngine.authorize()` (`core/engine.py`), which
   checks local wallet expiry/budget/headroom only. Central policy evaluation
   lives in `MintryWallet.check_authorization()` (OPA + `PolicyCache`) and is
   **not** invoked by the interceptor. Principle 1 (“governance changes without
   code changes”) is therefore incomplete for control-plane mandates.

2. **Signature verification is optional / incomplete.**
   Without a configured public key, fetched bundles are accepted unsigned.
   Disk cache is loaded without re-verification. Dashboard signing uses a
   different key env name and a non-canonical payload (see §2).

3. **Concurrent overspend window.**
   Pre-flight checks fixed `$0.01` headroom and does not reserve estimated cost;
   metering is post-response and asynchronous. Concurrent requests can all pass
   before spend catches up.

4. **Interception surface is narrow.**
   Only `httpx` + four provider host patterns. `requests`, `aiohttp`, custom
   gateways, streaming/non-200 success paths, and unrecognized hosts bypass
   metering/enforcement.

5. **`mintry.mandate()` does not auto-route.**
   Callers still need `X-Mintry-Mandate` (or accept the default mandate id).

6. **Durability / immutability soft spots.**
   Queued wallet writes can be lost on crash; writer errors are logged and
   dropped. Policy persistence uses `INSERT OR REPLACE` in places that conflict
   with “immutable versioned fact” language. Dashboard upsert/revoke mutates
   local mandates without going through signed central policy.

7. **Telemetry batcher not wired into `init()`.**
   `TelemetryBatcher` exists and is tested in isolation but is not started by
   the public init path.

### Six Principles scorecard (Python)

| Principle | Status |
| --- | --- |
| 1. Initialize once | Partial — hooks install once; repeated `init()` can desync engine closures |
| 2. Author centrally, versioned | At risk — local dashboard mutations; policy row replace/rollback semantics |
| 3. Enforce locally | Met for local wallet checks; **central policies not applied** |
| 4. Async sync + visible staleness | Partial — polling exists; fetch failures often look like “no update” |
| 5. Fail last-known-good | Partial — cache swap preserves prior on bad signature when verification is on |
| 6. Deterministic hot path | Met — no control-plane I/O inside interceptor allow/block |

---

## 2. Dashboard (`apps/dashboard`)

### Purpose

Next.js 16 / React 19 App Router UI for spend KPIs, audit feed, mandate
create/update/revoke, and “Sign & Push” policy bundles. Browser talks only to
same-origin BFF routes; those proxy the Python API and/or Supabase.

### Stack and shape

- Next `16.2.6`, React `19.2.4`, Tailwind 4, Chart.js, Supabase JS.
- Almost all UI in one client page: `src/app/page.tsx` (~533 lines).
- Routes:
  - `GET /api/summary` — Python summary + Supabase policy version enrichment
  - `POST /api/mandates/upsert|revoke` — transparent proxy to Python
  - `POST /api/policies/sign` — version, (optionally) sign, insert into Supabase
- Proxy helper: `src/lib/mintry-api.ts` → `MINTRY_DASHBOARD_API_ORIGIN`
  (default `http://127.0.0.1:8000`).

### Strengths

- Networking stays off the enforcement path.
- BFF keeps ledger and secrets off the browser.
- UI surfaces policy version / last sync / health (Principle 4 intent).
- Policy inserts are append-style rows keyed by agent + version.

### Highest-priority risks

| # | Issue | Why it matters |
| --- | --- | --- |
| 1 | **No auth** on any admin route | Anyone who can reach the UI/API can allocate budgets or publish policy |
| 2 | **Signing incompatible with Python verify** | Next signs `JSON.stringify(payload)`; Python verifies canonical sorted JSON (`crypto.py`). Real signatures will fail verification |
| 3 | **Env name mismatch** | Route reads `MINTRY_PRIVATE_KEY`; docs/`.env.example` use `MINTRY_POLICY_PRIVATE_KEY` |
| 4 | **Mock signature fallback** | Missing key → `mock_signature_for_phase2_spike` — conflicts with “reject unsigned” |
| 5 | **Dashboard `init` omits public key** | Verification not enabled in the common local dashboard path |
| 6 | **Topology** | Standalone Vercel cannot reach customer `127.0.0.1:8000` SQLite API |
| 7 | **Polling cost** | Client refreshes every 3s; each summary may flush SQLite, query ledger, health-check control plane, and scan all `policy_bundles` |
| 8 | **`has_expiry` always `False`** | Python summary computes expiry presence then hard-codes `False` (`dashboard.py`) |
| 9 | **Charts from last 100 audit rows** | “Cumulative spend” may not match true historical totals |
| 10 | **No Next/React tests; monolithic page** | Regression risk as UI grows |

Open the UI at `http://localhost:3000` (not `127.0.0.1`) — Next 16
`allowedDevOrigins` otherwise blocks the client bundle.

---

## 3. Sync API (`apps/sync-api`)

### Purpose (actual)

Legacy Express 5 stub with JSON-file persistence for mandate upsert/revoke,
additive spend ingest (`POST /api/v1/sync`), and summary. Documented in
`ARCHITECTURE.md` as a **local-development stub**; production control plane is
Supabase.

### Risks if treated as production

- No authentication; unrestricted CORS.
- In-place mandate mutation (not immutable versioned policy).
- No signatures, versions, polling contract, or last-known-good.
- `/api/v1/sync` is aggregate spend ingest, not WAL sync; no idempotency →
  retries double-count.
- Default store under `/tmp` (ephemeral); non-atomic writes; parse failure
  resets state to empty.
- Expiry stored but never evaluated; unknown sync IDs create zero-budget active
  mandates.
- `node_modules` committed; tests intentionally fail (`npm test`).

**Recommendation:** Keep for demos only. Prefer docs that point operators at
Supabase + Python polling. Avoid expanding this service toward production
control-plane duties.

---

## 4. Node SDK (`packages/mintry-node`)

### Purpose

TypeScript mirror of Python ergonomics: `init()`, scoped `mandate()`, global
`fetch` monkey-patch, SQLite wallet, structured `MintryMandateExceeded`.

### Maturity assessment

Despite package version `1.0.0`, this is a **prototype**:

- No control-plane client, policy cache, signatures, telemetry, webhooks,
  dashboard/CLI, or Prometheus/OTel.
- Only three basic tests; `npm test` not wired; `tsc` currently fails under
  TypeScript 6 (`moduleResolution: "node"`).
- `package.json` `main` points at missing root `index.js`; no build/`exports`/
  publish config.
- Metering largely OpenAI-shaped; Anthropic/Gemini schemas and streaming missed.
- Same `$0.01` headroom / concurrent overspend class of issues as Python.
- Hard-coded intent blocklist not centrally versioned.
- Committed `node_modules`.

Useful as a design sketch for multi-language enforcement; not shippable as a
peer of the Python SDK without a packaging and policy-sync pass.

---

## 5. Tools

| Tool | Notes |
| --- | --- |
| `tools/gemini-mock-server` | Dependency-free Go Gemini-compatible mock (~10 ms). Good latency baseline. |
| `tools/k6` | Load and concurrency scripts. Some docs describe a TCP proxy model that the product does not implement; at least one baseline script hits the mock **without** SDK interception. Interpret results carefully. |

---

## 6. Cross-cutting findings

### Architecture loop is open

Intended:

```text
Dashboard signs policy → Supabase → SDK polls → verify → PolicyCache → enforce
```

Observed:

```text
Dashboard may mock-sign / mis-sign → Supabase
SDK can poll into PolicyCache
Interceptor enforces local SQLite wallet only (not PolicyCache)
Dashboard can also mutate local mandates directly
```

Until interceptor authorization consults the verified cache (without network or
slow OPA CLI on the hot path), central governance changes do not govern traffic.

### Security

- Dashboard and sync-api expose privileged money/policy operations without auth.
- Service-role Supabase key usable from unauthenticated Next routes when
  configured.
- Python dashboard API uses `Access-Control-Allow-Origin: *`.
- Docs (`DEPLOYMENT.md`) already note missing auth — treat as hard blocker for
  any shared/public deployment.

### Documentation drift

- Roadmap still lists several Phase-1 policy items that have partial code
  (`PolicyCache`, polling) but are not end-to-end enforced.
- `DEPLOYMENT.md` still elevates sync-api in places that conflict with
  `ARCHITECTURE.md`.
- Dashboard app README remains create-next-app boilerplate.
- Release notes claim contextvars mandate scoping that the Python interceptor
  does not implement (header-based routing only).

### Testing gaps (highest leverage)

- No E2E test: signed central policy → poll → interceptor blocks/allows.
- No assertion that enforcement path performs zero outbound control-plane calls.
- No concurrent overspend / wallet durability stress coverage.
- No dashboard route auth or signing/canonicalization tests.
- Flaky free-threaded timing tests around metering/telemetry queues (known;
  treat as timing, not product breakage).

---

## 7. Recommended priority order

Ordered by architectural leverage, not calendar estimates. The full execution
plan (workstreams P0–P7, acceptance criteria, PR slices) lives in
[`PRODUCTION_READINESS_PLAN.md`](./PRODUCTION_READINESS_PLAN.md).

1. **Close the enforce loop:** route interceptor pre-flight through verified
   local policy state (deterministic numbers/rules only; no network; no slow
   CLI on the hot path).
2. **Make signing/verification one contract:** shared canonical JSON, ES256,
   matching env names (`MINTRY_POLICY_*`), reject unsigned when keys configured;
   remove mock-signature success path for real deployments.
3. **Authenticate dashboard mutations** before any non-localhost exposure.
4. **Fix summary bugs that undermine credibility:** `has_expiry`, chart vs
   total spend, per-row sync display, 3s poll + control-plane health cost.
5. **Label or quarantine legacy pieces:** sync-api and Node SDK clearly marked
   demo/prototype; stop documenting them as production control plane / peer SDK
   until they meet the principles.
6. **Hardening:** reserve-or-serialize spend against concurrent overshoot;
   meter streaming; broaden or explicitly document interception limits;
   wire or remove dead telemetry init path.

---

## 8. What “good” looks like for the next analysis checkpoint

- A test proves: unsigned/invalid policy rejected; last-known-good still
  enforces; new signed version changes allow/block within one poll interval.
- Dashboard cannot publish or mutate without auth in any shared environment.
- Sign (Next) and verify (Python) use the same payload bytes.
- Roadmap / deployment docs match the live topology (Supabase + Python;
  sync-api = stub).
- Node package either demoted from `1.0.0` or brought to a publishable subset
  of the Python surface with working build and tests.
