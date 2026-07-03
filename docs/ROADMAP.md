# Mintry Fabric Roadmap

This roadmap reflects the code currently present in the repository and the remaining work before a true production-ready `v1.0.0`.

> [!IMPORTANT]
> **Architectural Alignment:** All items on this roadmap, including "Ideas Under Consideration", are strictly subject to validation against the [Six Architecture Principles](ARCHITECTURE.md). Any feature that compromises deterministic, zero-latency local enforcement will be removed from the roadmap.

## Repository Status

The implementation currently covers the roadmap milestones through `v0.5.0`:

- sync and async interception
- multi-provider metering and per-model pricing
- mandate lifecycle and expiry enforcement
- audit log and CLI inspection
- local observability dashboard
- dashboard-driven mandate allocation and revocation
- JSON logs and webhook notifications

## Completed Milestones

### v0.1.1 - Patch

- [x] Fix `Decimal` import usage in wallet top-up flow
- [x] Replace hardcoded mandate routing with header-based routing
- [x] Add `MintryWallet.create_mandate()`
- [x] Add `MintryWallet.exhaust_mandate()`
- [x] Improve budget failure messages with mandate details

### v0.2.0 - Async Support

- [x] Patch `httpx.AsyncClient.send`
- [x] Provide async-safe interception flow using separate request-time database connections where needed
- [x] Keep `PolicyEngine.authorize()` usable in both sync and async interception paths
- [x] Add async coverage in the test suite

### v0.3.0 - Multi-Provider Support

- [x] Anthropic metering
- [x] Gemini metering
- [x] Mistral metering
- [x] Per-model pricing table
- [x] Provider-agnostic mandate routing

### v0.4.0 - Mandate Lifecycle and Governance

- [x] Mandate expiry enforcement
- [x] ES256 signature verification helpers for `AP2IntentMandate`
- [x] Status transitions: `active`, `exhausted`, `expired`
- [x] Append-only audit log
- [x] CLI mandate listing and inspection

### v0.5.0 - Observability and Dashboard

- [x] Local web dashboard
- [x] Structured JSON logs
- [x] Webhook alerts
- [x] Dashboard-driven budget allocation and revoke controls
- [x] Shared SDK/dashboard workflow against the same SQLite ledger

## Phase 1 — Alpha (Control Plane Upgrade)

See [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md) for full detail.

### Dashboard credibility (§10 — do first)

- [ ] Remove integration-test data from prospect-visible environments
- [ ] Hide Expiry column until meaningful
- [ ] Brand palette color consistency
- [ ] Live Audit Feed: ALLOW / BLOCK / THROTTLE events, above the fold
- [ ] KPI reframe: Protected Spend / Requests Blocked / Overspend Prevented

### Policy plane

- [ ] Polling policy sync (15–30s), version number, atomic swap
- [ ] Local last-known-good policy cache
- [ ] Signature verification on policy payloads before apply
- [ ] Rollback semantics: ledger independent of policy version
- [ ] Agent-grouped ledger view (UI layer)

### Control plane infrastructure

- [ ] Vercel + Supabase (skip Turso in Phase 1)
- [ ] Batched telemetry POST from SDK to control plane

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

- Package version, CHANGELOG, and documentation are now aligned to the `v0.5.0` feature set.
- Documentation in this folder is written against the current code in `src/mintry`.
- Remaining v1.0.0 blockers: Docker packaging, deployment guidance, TypeScript SDK, and stable public API promotion.
