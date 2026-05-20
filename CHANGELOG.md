# Changelog

All notable changes to Mintry Fabric are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [Unreleased]

_No unreleased changes._

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

## [0.1.1] - 2026-05-02

### Added

- `MintryWallet.create_mandate()`
- `MintryWallet.exhaust_mandate()`
- dynamic mandate routing through `X-Mintry-Mandate`
- real `PolicyEngine.shield()` lifecycle support

### Fixed

- fixed `Decimal` usage in wallet top-up flows
- removed the old hardcoded mandate routing path by preferring request headers

### Changed

- budget failure errors now include mandate, budget, spent, and remaining headroom details
- `MintryWallet.get_mandate()` now returns status and expiry metadata in addition to budget and spend

## [0.1.0] - 2026-04-30

### Added

- `mintry.init(api_key)` bootstrap entrypoint
- `MintryWallet` SQLite ledger with WAL enabled
- initial synchronous HTTPX interception
- OpenAI metering path
- `PolicyEngine` authorization flow
- `AP2IntentMandate` model scaffold
- Stripe mock bridge helper

[Unreleased]: https://github.com/ZolileN/mintry-fabric/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/ZolileN/mintry-fabric/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ZolileN/mintry-fabric/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ZolileN/mintry-fabric/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ZolileN/mintry-fabric/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/ZolileN/mintry-fabric/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ZolileN/mintry-fabric/releases/tag/v0.1.0
