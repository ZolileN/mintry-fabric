# Mintry Fabric Roadmap

This roadmap reflects the code currently present in the repository.

> [!IMPORTANT]
> **Architectural Alignment:** All items on this roadmap, including "Ideas Under Consideration", are strictly subject to validation against the [Six Architecture Principles](ARCHITECTURE.md). Any feature that compromises deterministic, zero-latency local enforcement will be removed from the roadmap.

## Repository Status

**Current release: `v1.3.0`** (background-first governance — auto-attribution, alerts, telemetry, simpler dashboard).

See [PHASE2_PLAN.md](./PHASE2_PLAN.md), [PRODUCTION_READINESS_PLAN.md](./PRODUCTION_READINESS_PLAN.md),
[RELEASE_NOTES_v1.3.0.md](./RELEASE_NOTES_v1.3.0.md), and [CHANGELOG.md](../CHANGELOG.md).

### Supported product path

| Layer | Status |
| --- | --- |
| Python SDK + local SQLite WAL | **Supported** — enforce locally, zero CP I/O on allow/block |
| Dashboard Sign & Push → Supabase | **Supported** — simple budget form + advanced JSON |
| Fleet telemetry ingest | **Supported** — `telemetry_events` batch upload + dashboard merge |
| Proactive alerts | **Supported** — webhook/Slack/email thresholds + weekly digest |
| Stripe top-up webhook | **Supported** — `POST /api/stripe/webhook` → ledger top-up |
| Fleet Option A / Org compile → flat caps | **Supported** — compiled before the hot path |
| Go `mintry-proxy` sidecar | **Scaffold** — HTTP metering works; HTTPS MITM TBD |
| Node SDK (`mintry-node`) | **Prototype** — private `0.1.0` |
| Legacy `apps/sync-api` | **Demo stub only** — not the control plane |

### Promise alignment (v1.1.1)

- With `MINTRY_CONTROL_PLANE_URL` set, local mandate upsert/revoke requires `MINTRY_LOCAL_GOVERNANCE=1`
- Dashboard leads with Sign & Push / Fleet / Org; local ledger edits are gated
- README / SECURITY honestly label supported vs scaffold paths

## Completed Milestones

### v0.1.1 – v0.5.0

Prior milestones (interception, async, multi-provider, lifecycle, dashboard) — see git history / CHANGELOG.

### v1.0.0 — Phase 1 production gate (2026-07-28)

- [x] Canonical ES256 policy contract (Python + dashboard)
- [x] PolicyCache wired into `PolicyEngine.authorize()`
- [x] Dashboard admin token / login cookie; Python API bearer
- [x] Spend reservations + durable flush/`close()`
- [x] TelemetryBatcher from `init()`
- [x] Idempotent `init()`; DoD test suites
- [x] Legacy sync-api / Node SDK honesty labels
- [x] Dashboard credibility (§10): demo mode, KPIs, audit feed, brand palette
- [x] Closed control-plane loop: sign → poll → verify → enforce; LKG on failure

### v1.1.0 — Phase 2 enterprise gate (2026-07-28)

See [PHASE2_PLAN.md](./PHASE2_PLAN.md).

- [x] **E0** Fleet Option A static sub-budget partitioning
- [x] **E1** Agent-grouped ledger (UI)
- [x] **E2** Org hierarchy compile → flat agent caps
- [x] **E3** Go sidecar scaffold (`apps/sidecar` / `mintry-proxy`)
- [x] **E4** OPA compile-at-sync materialization (no CLI on hot path)
- [x] **E5** Vault alias-only secret references

### v1.2.0 — Supabase Auth UI (2026-07-28)

- [x] Dashboard `/login` — email/password + magic link (Supabase Auth)
- [x] Middleware session refresh + production UI gate
- [x] Mutating APIs accept Supabase session (subject = email) or admin token break-glass
- [x] Optional `MINTRY_DASHBOARD_ALLOWED_EMAILS` allowlist
- [x] Sign out + session badge in nav

### v1.1.1 — Promise alignment (2026-07-28)

- [x] Central Sign & Push default when control plane configured
- [x] Local ledger mutations opt-in (`MINTRY_LOCAL_GOVERNANCE`)
- [x] Dashboard authoring UX reordered; docs honesty pass

### v1.3.0 — Background-first governance (2026-08-25)

- [x] ContextVar auto-attribution from `mintry.mandate()` (no per-request headers)
- [x] Sane default mandate (`default_agent`, configurable budget)
- [x] Telemetry wired from enforcement path to `telemetry_events`
- [x] Anthropic token metering + unknown-model warnings
- [x] Threshold alerts (80/95/100%) via webhook/Slack/email
- [x] Weekly spend digest worker
- [x] Dashboard: simple budget form, onboarding, terminology, local-mode UX
- [x] Fleet telemetry merge in dashboard summary API
- [x] Stripe checkout webhook → `/api/topup`
- [x] Sidecar default mandate → `default_agent`

## Next (post–v1.3.0)

Ordered by leverage for the stated promise ("init once / author centrally / enforce locally / any language"):

1. **Sidecar HTTPS MITM** — inspect/meter TLS LLM traffic through `HTTP(S)_PROXY` without uninspected tunnels
2. **Sidecar policy poller** — same verify → LKG → flat-cap loop as the Python SDK (today Python syncs; sidecar reads ledger)
3. ~~**Full Supabase Auth UI**~~ — done in `v1.2.0` (email/password + magic link; admin token break-glass)
4. ~~**Configurable intent blocklists**~~ — partial (hardcoded list; signed policy follow-up)
5. **Option B fleet hard cap** — Redis/Upstash atomic counter only if Option A partitions prove insufficient
6. **Org RBAC / profiles table** — map authenticated users to agent allowlists beyond email allowlist env
7. ~~**Automated Stripe-triggered top-ups**~~ — webhook path shipped in v1.3.0; self-serve Checkout UI follow-up

## Explicitly Deferred

From [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md) §8 — do not pull onto the hot path:

- Automatic model rerouting
- Anomaly / recommendation engine (analytics layer only)
- Push-based policy propagation (until enterprise SLA requires it)

## Ideas Under Consideration

- Shared ledger mode beyond a single local SQLite file (per-pod emptyDir + Option A remains preferred)
- VS Code spend visibility
- Automated Stripe-triggered top-ups — **webhook shipped v1.3.0**; hosted Checkout UI optional
- Publishable Node SDK subset once it matches Python’s closed enforce loop

## Notes

- Docs in this folder track code under `src/mintry`, `apps/dashboard`, and `apps/sidecar`.
- Phase 1 = `1.0.0`. Phase 2 = `1.1.0`. Promise tighten = `1.1.1`.
- Next work must preserve: no network on authorize; fail to last-known-good; deterministic allow / block / configured number.
