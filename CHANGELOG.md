# Changelog

All notable changes to Mintry Fabric are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [Unreleased]

This repository currently contains a post-`0.1.0` development snapshot with features implemented through the roadmap’s `v0.5.0` milestone.

### Added

- async interception via `httpx.AsyncClient.send`
- dynamic mandate routing through `X-Mintry-Mandate`
- real `PolicyEngine.shield()` lifecycle support for shared and ephemeral mandates
- mandate expiry tracking and automatic status transition to `expired`
- append-only `mandate_audit_log` ledger history
- CLI commands:
  - `mintry mandates list`
  - `mintry mandates inspect <id>`
  - `mintry dashboard`
- local observability dashboard with:
  - KPI summary
  - mandate ledger
  - top-spend list
  - audit feed
  - mandate create/update/revoke endpoints
- JSON structured log output controlled by `MINTRY_JSON_LOGS=1`
- webhook dispatch for authorization failures and shield exhaustion
- provider-aware pricing registry for OpenAI, Anthropic, Gemini, and Mistral
- `register_model()` and `list_models()` pricing helpers
- `AP2IntentMandate` ES256 signature verification and `sign_mandate()` test helper

### Changed

- interceptor installation is now idempotent and can be reset for tests
- budget failure errors now include mandate, budget, spent, and remaining headroom details
- `mintry.init()` validates `api_key` and accepts `db_path` and `webhook_url`
- `MintryWallet.get_mandate()` now returns status and expiry metadata in addition to budget and spend

### Fixed

- removed the old hardcoded mandate routing path by preferring request headers
- fixed `Decimal` usage in wallet top-up flows
- fixed double-metering caused by stacked interceptor patches

## [0.1.0] - 2026-04-30

### Added

- `mintry.init(api_key)` bootstrap entrypoint
- `MintryWallet` SQLite ledger with WAL enabled
- initial synchronous HTTPX interception
- OpenAI metering path
- `PolicyEngine` authorization flow
- `AP2IntentMandate` model scaffold
- Stripe mock bridge helper

[0.1.0]: https://github.com/ZolileN/mintry-fabric/releases/tag/v0.1.0
