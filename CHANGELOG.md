# Changelog

All notable changes to **Mintry Fabric** will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

---

## [Unreleased]

### Planned
- Async HTTPX transport patching (`httpx.AsyncClient.send`)
- Multi-provider support (Anthropic, Gemini, Mistral)
- Mandate expiry enforcement
- CLI dashboard for real-time ledger inspection
- Remote sync of spend data to Mintry monitoring plane

---

## [0.1.0] — 2026-04-30

### Added
- **`mintry.init(api_key)`** — One-call initializer that wires the Logic Fabric into the global HTTPX transport layer.
- **`MintryWallet`** — SQLite-backed local ledger with Write-Ahead Logging (WAL) for thread-safe mandate tracking.
  - `check_authorization(mandate_id, cost)` — Pre-flight budget check with atomic deduction.
  - `record_usage(mandate_id, actual_cost)` — Post-flight token cost attribution.
  - `add_funds(mandate_id, amount)` — Increases the `max_usd` ceiling on a mandate.
  - `get_mandate(mandate_id)` — Fetches live budget and spend data for a mandate.
  - `get_spent(mandate_id)` — Returns cumulative spend for a mandate.
- **`PolicyEngine`** — Gatekeeper that authorizes or denies requests based on remaining mandate budget.
  - `authorize(mandate_id, request, deduct)` — Two-phase authorization (pre-flight check, optional deduction).
  - `shield(task, max_usd)` — Context manager for scoped mandate enforcement.
- **`GlobalHTTPInterceptor`** — Monkey-patches `httpx.Client.send` to intercept all outbound LLM traffic.
  - Pre-flight fiscal check before any token is consumed.
  - Post-flight token metering using `usage` metadata from provider response.
  - Intent-based security filter blocking prohibited prompt patterns.
- **`AP2IntentMandate`** — Pydantic model for AP2-compliant mandate payloads with BBS+/ES256 signature support.
- **`MppBridge`** — Stripe integration bridge for mandate top-up flows.
- SQLite database auto-provisioned at `~/.mintry/vouchers.db` on first run.
- `pytest-httpx` test suite covering metering delta validation, fabric interception, and intent checking.
- No-GIL compatibility for Python 3.14+ free-threaded environments.
- MIT License.

### Known Limitations
- Async `httpx.AsyncClient` is not yet patched — only sync clients are intercepted in this release.
- `mandate_id` is currently hardcoded to `mt_task_882x` in the interceptor; dynamic routing via `X-Mintry-Mandate` header is planned.
- `add_funds` references `Decimal` without importing it (known bug, tracked for 0.1.1).

---

[Unreleased]: https://github.com/ZolileN/mintry-fabric/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ZolileN/mintry-fabric/releases/tag/v0.1.0
