# Mintry Fabric: Roadmap

This roadmap outlines planned features, improvements, and milestones. It is a living document and subject to change based on team priorities and user feedback.

---

## Current Release: v0.3.0

Core Logic Fabric is live with synchronous and asynchronous HTTPX interception, multi-provider token metering (OpenAI, Anthropic, Gemini, Mistral), per-model pricing lookup, and cryptographic mandate validation (ES256 + expiry).

---

## v0.1.1 — Patch (Near-term)

> Bug fixes and known limitations from the initial release.

- [x] Fix `Decimal` import missing in `wallet.add_funds`
- [x] Fix hardcoded `mt_task_882x` mandate ID in `GlobalHTTPInterceptor` — route dynamically via `X-Mintry-Mandate` header
- [x] Add `MintryWallet.create_mandate(mandate_id, max_usd)` public method
- [x] Add `MintryWallet.exhaust_mandate(mandate_id)` for cleanup
- [x] Improve error messaging to include mandate ID and remaining budget in `PermissionError`

---

## v0.2.0 — Async Support

> Unblock teams using async agent frameworks.

- [x] Patch `httpx.AsyncClient.send` for full async interception
- [x] Support `asyncio`-safe SQLite writes (connection-per-thread or `aiosqlite`)
- [x] Async-compatible `PolicyEngine.authorize`
- [x] Update test suite with async fixtures

---

## v0.3.0 — Multi-Provider Support

> Extend beyond OpenAI to cover the full LLM provider landscape.

- [x] Anthropic (`api.anthropic.com`) token metering
- [x] Google Gemini (`generativelanguage.googleapis.com`) token metering
- [x] Mistral (`api.mistral.ai`) token metering
- [x] Per-provider token pricing table (configurable, with live update mechanism)
- [x] Provider-agnostic mandate routing

---

## v0.4.0 — Mandate Lifecycle & Governance

> Full mandate management for production use.

- [x] Mandate expiry enforcement using `AP2IntentMandate.expires_at`
- [x] `AP2IntentMandate` signature verification (BBS+, ES256)
- [x] Mandate status transitions: `active` → `exhausted` → `expired`
- [x] Mandate audit log (immutable append-only table)
- [x] CLI: `mintry mandates list`, `mintry mandates inspect <id>`

---

## v0.5.0 — Observability & Dashboard

> Real-time visibility into agent spend and mandate health.

- [ ] Local web dashboard (Spend by mandate, time-series chart, top agents by cost)
- [ ] Structured JSON log output for integration with Datadog, Grafana, or similar
- [ ] Webhook support for mandate exhaustion events
- [ ] Remote sync of ledger data to Mintry monitoring plane

---

## v1.0.0 — Production-Ready Release

> Hardened, fully documented, and suitable for team-wide deployment.

- [ ] All known bugs from 0.x resolved
- [ ] Stable public API with semantic versioning guarantee
- [ ] Full async + sync support
- [ ] Complete API reference and integration guides
- [ ] Docker-based deployment option for shared team ledger
- [ ] SDK clients for TypeScript/JavaScript agent ecosystems

---

## Ideas Under Consideration

These are not yet scheduled but have been discussed:

- **Per-model pricing overrides** — [x] Completed (via `register_model` pricing API)
- **Shared ledger mode** — One central `vouchers.db` served over a local network for multi-agent teams.
- **VS Code extension** — Inline spend display while writing agent code.
- **Stripe top-up automation** — Automatically top up mandates via Stripe when spend approaches the ceiling.

---

## Feedback

Have a feature request or priority suggestion? Open a GitHub Discussion or mention it in your next PR.
