# Mintry Fabric Sprint Plan

**Updated:** 2026-05-20  
**Repository State Under Review:** post-`0.5.0` feature snapshot

This document is now a short planning snapshot rather than the original bug-fix checklist. Most of the earlier sprint work is already implemented in the repo.

## Completed Delivery Lanes

### Lane 1: Core Stabilization

- [x] idempotent interceptor installation
- [x] dynamic mandate routing
- [x] real mandate create/exhaust lifecycle
- [x] richer `PermissionError` messages
- [x] API key validation in `mintry.init()`

### Lane 2: Async and Pricing

- [x] async `httpx` interception
- [x] per-model pricing registry
- [x] custom model registration
- [x] async enforcement and intent-blocking tests

### Lane 3: Governance and Lifecycle

- [x] mandate expiry enforcement
- [x] append-only audit log
- [x] signed mandate verification helpers
- [x] CLI mandate inspection

### Lane 4: Observability

- [x] JSON log output
- [x] webhook notifications
- [x] local dashboard server
- [x] dashboard-driven mandate allocation and revoke flow
### Lane 5: Python "Three Lines" Ergonomics (Phase 1)

- [x] `MintryMandateExceeded` custom exception with structured budget attributes
- [x] global `mintry.mandate` context manager
- [x] `MINTRY_API_KEY` environment variable fallback for `init()`
- [x] backwards-compatible test suite enforcement

### Lane 6: Node.js SDK & Sidecar Blueprint (Phases 2 & 3)

- [x] TypeScript SDK wrapper using `AsyncLocalStorage` for mandate scoping
- [x] Shared state via synchronous `better-sqlite3` driver
- [x] Fetch interceptor for LLM budget enforcement
- [x] ADR-003: Language-Agnostic Sidecar Proxy architecture (Go daemon)

## Current Test Coverage Areas

The test suite now covers:

- metering and enforcement
- intent blocking
- Stripe mock top-up flow
- dynamic mandate routing and `shield()`
- pricing and async interception
- audit log and CLI behaviour
- observability dashboard endpoints
- allocated-budget reuse against the dashboard-backed ledger

## Next Sprint Priorities

### Release Readiness

- [x] reconcile package versioning with implemented feature set
- [ ] run the full test suite in a clean synced environment and record the release baseline
- [ ] tighten docs around supported deployment models

### Production Packaging

- [ ] add Docker packaging for a shared ledger deployment option
- [ ] define and freeze the supported public API surface
- [ ] prepare release notes for the first post-`0.1.0` tagged release

### Ecosystem Expansion

- [ ] TypeScript/JavaScript SDK
- [ ] configurable policy surface for blocklists and defaults
- [ ] optional remote sync client implementation beyond local hooks
