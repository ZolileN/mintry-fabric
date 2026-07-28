# Changelog

All notable changes to Mintry Fabric are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [1.2.0] - 2026-07-28

### Added

- Full Supabase Auth UI for the dashboard (`/login`): email/password, magic link, PKCE callback
- Middleware session refresh; production UI redirects to `/login` when unauthenticated
- Mutating APIs accept Supabase session (`issued_by` = user email) with optional `MINTRY_DASHBOARD_ALLOWED_EMAILS`
- Admin token remains break-glass (login tab + Bearer / cookie)
- Nav session badge + Sign out

## [1.1.1] - 2026-07-28

### Changed

- Tighten promise alignment: with a control plane configured, local mandate upsert/revoke requires `MINTRY_LOCAL_GOVERNANCE=1`; Sign & Push is the default authoring path
- Dashboard UI: Sign & Push / Fleet / Org first; local ledger edits demoted and gated
- README / SECURITY / sidecar README honest about supported vs scaffold paths

## [1.1.0] - 2026-07-28

### Added

- Phase 2 complete (E0–E5): see `docs/PHASE2_PLAN.md`
- E0: Fleet Option A (`mintry.core.fleet`, `POST /api/fleets/partition`)
- E1: Agent-grouped ledger rollups
- E2: Org hierarchy compile (`mintry.core.org`, `POST /api/orgs/compile`)
- E3: Go sidecar scaffold (`apps/sidecar` / `mintry-proxy`)
- E4: OPA compile-at-sync materialization (`materialize_flat_rules`); no CLI on hot path
- E5: Vault alias-only secrets (`mintry.core.secrets`, `POST /api/secrets/aliases`)

## [1.0.0] - 2026-07-28

### Added

- Closed control-plane enforce loop: verified `PolicyCache` caps are applied in `PolicyEngine.authorize()` on the hot path (no network I/O)
- Canonical ES256 policy signing shared by Python (`mintry.core.crypto`) and the dashboard (`apps/dashboard/src/lib/policy-crypto.ts`)
- Dashboard admin auth (`MINTRY_DASHBOARD_ADMIN_TOKEN`, `/api/login` cookie) and Python API bearer (`MINTRY_DASHBOARD_API_TOKEN`)
- Per-mandate spend reservations with release on failed / non-200 upstream calls
- `TelemetryBatcher` started from `mintry.init()` when the control plane is configured
- Idempotent `mintry.init()` for the same ledger path; `mintry.close()` flushes and resets hooks
- Production readiness docs: `docs/APP_ANALYSIS.md`, `docs/PRODUCTION_READINESS_PLAN.md`
- DoD test suites: `tests/test_production_readiness.py`, `tests/test_v1_dod.py`

### Changed

- Package version reflects a Phase 1 production gate (enforce loop + crypto + auth + hardening proofs)
- Dashboard KPIs reframed (Protected Spend / Requests Blocked / Overspend Prevented)
- Legacy `apps/sync-api` and experimental `packages/mintry-node` clearly labeled; Node package demoted to `0.1.0` private
- Deployment / security docs aligned to Supabase control plane (not the Express stub)

### Security

- Policy mock signatures disabled unless `MINTRY_ALLOW_MOCK_SIGNATURES=1`
- Disk last-known-good policy re-verified when a public key is configured
- CORS on the Python dashboard API locked to `MINTRY_DASHBOARD_UI_ORIGIN`

## [0.6.0] - 2026-07-28

Interim control-plane alpha (enforce loop + crypto + auth foundation). Superseded by 1.0.0 the same day once DoD tests landed.

## [0.5.0] - 2026-05-20

### Added

- local observability dashboard with:
  - KPI summary
  - mandate ledger
  - top-spend list
  - audit feed
  - mandate create/update/revoke endpoints
- JSON structured log output controlled by `MINTRY_JSON_LOGS=1`
- webhook dispatch for authorization failures and shield exhaustion
- CLI `mintry dashboard` command
- dashboard-driven budget allocation and revoke flow
- shared SDK/dashboard workflow against the same SQLite ledger
- `__version__` runtime attribute on the `mintry` package

### Changed

- `mintry.init()` validates `api_key` and accepts `db_path` and `webhook_url`
- package version bumped from `0.1.0` to `0.5.0` to reflect implemented feature set
- CHANGELOG restructured into versioned sections matching roadmap milestones

## [0.4.0] - 2026-05-15

### Added

- mandate expiry enforcement
- ES256 signature verification helpers for `AP2IntentMandate`
- status transitions: `active`, `exhausted`, `expired`
- append-only `mandate_audit_log` ledger history
- CLI commands:
  - `mintry mandates list`
  - `mintry mandates inspect <id>`

## [0.3.0] - 2026-05-10

### Added

- provider-aware pricing registry for OpenAI, Anthropic, Gemini, and Mistral
- `register_model()` and `list_models()` pricing helpers
- per-model pricing table

## [0.2.0] - 2026-05-05

### Added

- async interception via `httpx.AsyncClient.send`
- `PolicyEngine.shield()` context manager with shared and ephemeral mandate modes

### Changed

- interceptor installation is now idempotent and can be reset for tests
- `PolicyEngine.authorize()` usable in both sync and async interception paths

## [0.1.1] - 2026-04-28

### Fixed

- `Decimal` import usage in wallet top-up flow
- hardcoded mandate routing replaced with header-based routing

### Added

- `MintryWallet.create_mandate()`
- `MintryWallet.exhaust_mandate()`
- richer budget failure messages

## [0.1.0] - 2026-04-20

### Added

- initial `httpx` interception
- local SQLite WAL ledger
- basic mandate budget checks
