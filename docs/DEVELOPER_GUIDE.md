# Mintry Fabric: Developer Guide

**Release:** `v1.3.0`

Mintry intercepts supported LLM provider traffic at the `httpx` layer, enforces
budget caps from a local SQLite ledger, and syncs signed policies from Supabase
in the background.

## Quick start

```python
import mintry

mintry.init(api_key="mk_dev_example", db_path="test_data/local.db")

with mintry.mandate("research_task", cap=50.0):
    # All nested LLM calls inside this block are auto-attributed
    ...
```

No `X-Mintry-Mandate` header is required when using `mintry.mandate()`.

## Attribution order

For each outbound LLM request:

1. `X-Mintry-Mandate` header (explicit override)
2. Active `mintry.mandate()` / `engine.shield()` context (ContextVar)
3. `MINTRY_DEFAULT_MANDATE` or `MINTRY_AGENT_ID` (default `default_agent`)

The default mandate is seeded at `MINTRY_DEFAULT_BUDGET_USD` (default `$50`) — not a $0.01 trap.

## Mandate patterns

**Named budget (recommended):**

```python
with mintry.mandate("nightly_summarizer", cap=50.0):
    run_job()
```

**Pre-allocated dashboard budget:**

```python
with engine.shield("research_task") as mandate:
    assert mandate.id == "research_task"
```

**Ephemeral scoped mandate:**

```python
with engine.shield("one-off", max_usd=0.50) as mandate:
    ...
```

## What happens on each LLM call

1. Resolve mandate id (header → context → default)
2. `PolicyEngine.authorize()` — local budget + signed policy caps (no network)
3. Intent filter (hardcoded prohibited phrases)
4. Forward to provider
5. Meter tokens (OpenAI, Anthropic, Gemini, Mistral shapes)
6. Append audit log + async telemetry upload
7. Threshold alerts at 80/95/100% via webhook/Slack/email (async)

## Control plane sync

When `MINTRY_CONTROL_PLANE_URL` and keys are set:

- Policy poller fetches signed `policy_bundles` every ~20s
- `TelemetryBatcher` uploads decisions to `telemetry_events`
- Invalid signatures rejected; last-known-good policy kept

## Notifications

Configure async channels (never on the hot path):

- `MINTRY_WEBHOOK_URL` — generic JSON
- `MINTRY_SLACK_WEBHOOK_URL` — Slack incoming webhook
- `MINTRY_RESEND_API_KEY` + `MINTRY_ALERT_EMAIL_TO` — email via Resend
- Weekly digest: `MINTRY_DIGEST_INTERVAL_SEC` (default 7 days)

## Dashboard

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
cd apps/dashboard && npm run dev
```

Open **http://localhost:3000**. The UI includes:

- Spend overview + activity feed
- Simple budget form (agent + monthly cap)
- Proactive alerts panel + test button
- Policy sync status (local mode guidance)
- Advanced JSON editors (fleet, org, secrets)

## Stripe top-up

Point Stripe `checkout.session.completed` to `POST /api/stripe/webhook` on the
dashboard. Set `metadata.mandate_id` on the Checkout Session. Verified events
call `POST /api/topup` on the Python API to increase `max_usd`.

## Supported providers

Host-based interception for:

- `api.openai.com`
- `api.anthropic.com`
- `generativelanguage.googleapis.com`
- `api.mistral.ai`

Requires the client to use `httpx` (OpenAI SDK default).

## Design constraints

- [Six Architecture Principles](ARCHITECTURE.md) — no network on authorize
- Process-wide httpx monkey-patch
- Local SQLite ledger per agent process
- Go sidecar (`mintry-proxy`) scaffold for non-Python stacks

## Development loop

```bash
uv sync --dev
uv run pytest
uv run mintry dashboard --db test_data/local.db
```

See [CONFIGURATION.md](CONFIGURATION.md) for all environment variables.
