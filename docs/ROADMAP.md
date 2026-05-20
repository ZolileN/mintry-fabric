# Mintry Fabric Roadmap

This roadmap reflects the code currently present in the repository and the remaining work before a true production-ready `v1.0.0`.

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

## Remaining Work Before v1.0.0

### v1.0.0 - Production-Ready Release

- [ ] Resolve remaining known release/documentation mismatches
- [ ] Promote a stable public API and publish the corresponding package version
- [x] Full sync + async support
- [x] Complete Python integration and API reference docs
- [ ] Docker-based deployment option for a shared team ledger
- [ ] SDK clients for TypeScript/JavaScript ecosystems
- [ ] Clear deployment guidance for multi-process and multi-host usage

## Ideas Under Consideration

- shared ledger mode beyond a single local SQLite file
- VS Code spend visibility
- automated Stripe-triggered top-ups
- configurable intent blocklists instead of the current built-in phrases

## Notes

- The repo still needs release-management cleanup before it should be called `v1.0.0`.
- Documentation in this folder is written against the current code in `src/mintry`, not against an already-published production release.
