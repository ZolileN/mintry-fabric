# Mintry Fabric: Configuration Reference

**Release:** `v1.3.0` — see [CHANGELOG.md](../CHANGELOG.md).

This document lists configuration that is implemented in the current codebase.

## `mintry.init()` parameters

```python
engine = mintry.init(
    api_key="mk_dev_example",          # or MINTRY_API_KEY env
    db_path="~/.mintry/vouchers.db",
    webhook_url="https://example.com/hook",  # optional; see MINTRY_WEBHOOK_URL
    control_plane_url="https://xxx.supabase.co",
    control_plane_key="your-key",
    control_plane_public_key="-----BEGIN PUBLIC KEY-----...",
    policy_sync_interval=20.0,
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | `MINTRY_API_KEY` | Required non-empty API key |
| `db_path` | `~/.mintry/vouchers.db` | Local SQLite ledger |
| `webhook_url` | `MINTRY_WEBHOOK_URL` | Async alert webhook destination |
| `control_plane_url` | `MINTRY_CONTROL_PLANE_URL` | Supabase REST base URL |
| `control_plane_key` | `MINTRY_CONTROL_PLANE_KEY` | Supabase anon or service key |
| `control_plane_public_key` | `MINTRY_POLICY_PUBLIC_KEY` | ES256 public key for policy verify |
| `policy_sync_interval` | `20` | Policy poll interval (seconds) |

`mintry.init()` is idempotent for the same `db_path`. Call `mintry.close()` to flush workers.

## Environment variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTRY_API_KEY` | — | API key if not passed to `init()` |
| `MINTRY_AGENT_ID` | `default_agent` | Control-plane agent id + default mandate fallback |
| `MINTRY_DEFAULT_MANDATE` | `MINTRY_AGENT_ID` | Mandate id for unattributed LLM traffic |
| `MINTRY_DEFAULT_BUDGET_USD` | `50.0` | Seed budget for default mandate |
| `MINTRY_JSON_LOGS` | unset | `1` → JSON structured logs |

### Control plane

| Variable | Description |
|----------|-------------|
| `MINTRY_CONTROL_PLANE_URL` | Supabase project URL |
| `MINTRY_CONTROL_PLANE_KEY` | Anon key (reads) |
| `MINTRY_SERVICE_ROLE_KEY` | Service role (writes; dashboard + telemetry) |
| `MINTRY_POLICY_PUBLIC_KEY` | Verify signed policies on agents |
| `MINTRY_POLICY_PRIVATE_KEY` | Sign policies (Vercel only) |
| `MINTRY_REQUIRE_POLICY_SIGNATURES` | Fail closed when private key missing (dashboard) |
| `MINTRY_ALLOW_MOCK_SIGNATURES` | Dev-only mock signatures |
| `MINTRY_TELEMETRY_DISABLED` | `1` → skip telemetry batch upload |
| `MINTRY_LOCAL_GOVERNANCE` | `1` → allow local ledger upsert when CP configured |

### Notifications (async analytics — never on authorize hot path)

| Variable | Description |
|----------|-------------|
| `MINTRY_WEBHOOK_URL` | JSON webhook for threshold alerts + digests |
| `MINTRY_SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `MINTRY_RESEND_API_KEY` | Resend API key for email alerts |
| `MINTRY_ALERT_EMAIL_TO` | Alert recipient email |
| `MINTRY_ALERT_EMAIL_FROM` | Sender for Resend (default `alerts@mintry.local`) |
| `MINTRY_DIGEST_DISABLED` | `1` → disable weekly digest worker |
| `MINTRY_DIGEST_INTERVAL_SEC` | Digest interval (default `604800` = 7 days) |

Threshold alerts fire once per mandate at **80%, 95%, and 100%** utilization.

### Dashboard

| Variable | Description |
|----------|-------------|
| `MINTRY_DASHBOARD_ADMIN_TOKEN` | Break-glass admin login |
| `MINTRY_DASHBOARD_API_TOKEN` | Bearer token for Python data API |
| `MINTRY_DASHBOARD_API_ORIGIN` | Next.js → Python API (default `127.0.0.1:8000`) |
| `MINTRY_DASHBOARD_UI_ORIGIN` | CORS origin for Python API |
| `MINTRY_DASHBOARD_ALLOWED_EMAILS` | Comma-separated Supabase email allowlist |
| `MINTRY_REQUIRE_AUTH` | Force auth gate in development |
| `MINTRY_DEMO_MODE` | Hide integration-test mandates in dashboard |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Auth for dashboard login |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (browser) |

### Stripe top-up

| Variable | Description |
|----------|-------------|
| `STRIPE_WEBHOOK_SECRET` | Verify `POST /api/stripe/webhook` signatures |

Stripe `checkout.session.completed` events must include `metadata.mandate_id` (or `mintry_mandate_id`). Amount is taken from `amount_total` (cents).

## Attribution (no manual headers required)

```python
with mintry.mandate("my_agent", cap=50.0):
    client.chat.completions.create(...)  # auto-attributed via ContextVar
```

Resolution order for each LLM request:

1. `X-Mintry-Mandate` header (explicit override)
2. Active `mintry.mandate()` / `shield()` context
3. `MINTRY_DEFAULT_MANDATE` or `MINTRY_AGENT_ID` (`default_agent`)

## SQLite ledger

- WAL mode, async writer thread
- Tables: `mandates`, `mandate_audit_log`, `policy_versions`
- Seeds `default_agent` at `MINTRY_DEFAULT_BUDGET_USD` (not a $0.01 trap)

## Pricing

Built-in table in `src/mintry/core/pricing.py`. Extend at runtime:

```python
from mintry.core.pricing import register_model
register_model("ft:custom", input_rate=0.00001, output_rate=0.00003)
```

Token extraction supports OpenAI (`prompt_tokens`), Anthropic (`input_tokens`), and Gemini (`usageMetadata`).

Unknown models log a `meter_warning` audit event and use default pricing rates.

## Intent filter (hardcoded)

Blocked prompt phrases: `bypass wallet`, `disable mintry`, `delete vouchers.db`.
