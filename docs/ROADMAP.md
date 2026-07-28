# Mintry Fabric Roadmap

This roadmap reflects the code currently present in the repository.

> [!IMPORTANT]
> **Architectural Alignment:** All items on this roadmap, including "Ideas Under Consideration", are strictly subject to validation against the [Six Architecture Principles](ARCHITECTURE.md). Any feature that compromises deterministic, zero-latency local enforcement will be removed from the roadmap.

## Repository Status

**Current release: `v1.0.0` (Phase 1 production gate).** See
[PRODUCTION_READINESS_PLAN.md](./PRODUCTION_READINESS_PLAN.md) and
[CHANGELOG.md](../CHANGELOG.md).

Implemented:

- sync and async interception with local SQLite WAL ledger
- multi-provider metering and per-model pricing
- mandate lifecycle, expiry, audit log, CLI
- local observability dashboard + admin auth
- closed control-plane loop: canonical ES256 sign → poll → verify → enforce
- batched telemetry; last-known-good policy cache

## Completed Milestones

### v0.1.1 – v0.5.0

Prior milestones (interception, async, multi-provider, lifecycle, dashboard) are complete — see git history / CHANGELOG.

### v1.0.0 — Phase 1 production gate (2026-07-28)

- [x] Canonical ES256 policy contract (Python + dashboard)
- [x] PolicyCache wired into `PolicyEngine.authorize()`
- [x] Dashboard admin token / login cookie; Python API bearer
- [x] Spend reservations + durable flush/`close()`
- [x] TelemetryBatcher from `init()`
- [x] Idempotent `init()`; DoD test suites
- [x] Legacy sync-api / Node SDK honesty labels

## Phase 1 — Alpha (Control Plane Upgrade)

See [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md) for full detail.

> **Status (v1.0.0):** Production readiness DoD is met for Phase 1.
> Sidecar / fleet / org hierarchy remain Phase 2.

### Dashboard credibility (§10)

- [x] Remove integration-test data from prospect-visible environments (`MINTRY_DEMO_MODE`)
- [x] Hide Expiry column until meaningful (`has_expiry`)
- [x] Brand palette color consistency (#050505 / #10B981)
- [x] Live Audit Feed: ALLOW / BLOCK / SPEND events, above the fold
- [x] KPI reframe: Protected Spend / Requests Blocked / Overspend Prevented

### Policy plane

- [x] Polling policy sync (15–30s), version number, atomic swap
- [x] Local last-known-good policy cache (disk LKG re-verified when key configured)
- [x] Signature verification on policy payloads before apply (canonical ES256)
- [x] Interceptor enforces verified PolicyCache caps (closed loop)
- [x] Rollback semantics: ledger independent of policy version
- [ ] Agent-grouped ledger view (UI layer) — deferred polish

### Control plane infrastructure

- [x] Vercel + Supabase (skip Turso in Phase 1)
- [x] Dashboard / admin authentication (admin token + login cookie; full Supabase Auth UI optional)
- [x] Batched telemetry POST from SDK to control plane
- [x] Canonical ES256 sign/verify + shared env names
- [x] Quarantine legacy `apps/sync-api`; honest `mintry-node` maturity label

## Phase 2 — Enterprise

- [ ] Go/Rust sidecar, Alpine Docker, K8s/ECS deployment
- [ ] Fleet budget: Option A static sub-budget partitioning
- [ ] Full Agent-as-primary data model + org/project hierarchy
- [ ] OPA bundle evaluation for policy distribution/signing
- [ ] Secrets orchestration via customer Vault (alias-only)

## Explicitly Deferred (§8)

- Automatic model rerouting
- Anomaly/recommendation engine
- Push-based policy propagation (until enterprise SLA requires it)

## Ideas Under Consideration

- shared ledger mode beyond a single local SQLite file
- VS Code spend visibility
- automated Stripe-triggered top-ups
- configurable intent blocklists instead of the current built-in phrases

## Notes

- Documentation in this folder is written against the current code in `src/mintry`.
- Phase 2 items are intentionally out of the `1.0.0` gate.
