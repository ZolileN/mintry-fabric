# Release Notes — v1.3.0

**Date:** 2026-08-25  
**Theme:** Background-first governance — tenants integrate once, get pinged only when needed.

## Highlights

### SDK — invisible enforcement

- **`mintry.mandate()` auto-attribution** — ContextVar injects mandate id; no `X-Mintry-Mandate` header required inside the block
- **Stable readable budget ids** — top-level `mandate("task_name", cap=50)` uses `task_name` as ledger id
- **Sane defaults** — `default_agent` seeded at `MINTRY_DEFAULT_BUDGET_USD` (default $50)
- **Fleet telemetry** — `TelemetryBatcher.record_decision()` wired from authorize + meter paths
- **Anthropic metering** — `input_tokens` / `output_tokens` supported
- **Unknown model warnings** — audit + telemetry `meter_warning` events
- **Threshold alerts** — async webhooks at 80%, 95%, 100% utilization
- **Weekly digest** — optional background worker (`MINTRY_DIGEST_INTERVAL_SEC`)

### Notifications

- `MINTRY_WEBHOOK_URL` — generic JSON alerts
- `MINTRY_SLACK_WEBHOOK_URL` — Slack incoming webhook
- `MINTRY_RESEND_API_KEY` + `MINTRY_ALERT_EMAIL_TO` — email via Resend

### Dashboard

- **Set Agent Budget** — 3-field form replaces raw JSON as primary workflow
- **Onboarding** — empty-state `mintry.init()` snippet
- **Proactive alerts panel** — channel status + test button
- **Local mode guidance** — green “local (healthy)” when control plane unconfigured
- **Fleet telemetry merge** — `telemetry_events` from Supabase in summary API
- Terminology pass (Tracked Spend, Activity Feed, Policy sync)

### Stripe top-up

- `POST /api/stripe/webhook` — verified `checkout.session.completed` → `POST /api/topup`
- Checkout Session metadata: `mandate_id` or `mintry_mandate_id`

### Sidecar

- Default mandate id → `default_agent` (aligned with Python SDK)

## Upgrade notes

1. Set `MINTRY_AGENT_ID` per deployment (defaults to `default_agent`)
2. Configure at least one notification channel for proactive alerts
3. Open dashboard at **http://localhost:3000** (not `127.0.0.1`)
4. Restart `mintry dashboard` after upgrade to pick up new API fields (`local_mode`, notifications)

## Docs

- [CONFIGURATION.md](CONFIGURATION.md) — full env reference rewritten for v1.3.0
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — attribution, alerts, Stripe
- [ROADMAP.md](ROADMAP.md) — v1.3.0 milestone
