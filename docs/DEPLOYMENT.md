# Mintry Fabric — Production Deployment Guide

**Supported stack (v1.2.0):** Next.js dashboard on **Vercel** + **Supabase** control plane + **Python SDK** enforcement on customer hosts.

> Auth stays on the dashboard. Agents enforce locally with **zero control-plane I/O** on allow/block.

```text
┌─────────────────────┐     signed policy_bundles      ┌──────────────────────────┐
│  Vercel Dashboard   │ ─────────────────────────────► │  Supabase                │
│  Sign & Push / Auth │ ◄──── telemetry (batched) ──── │  policy_bundles + events │
└─────────────────────┘                                └────────────▲─────────────┘
                                                                    │ poll 15–30s
                                                       ┌────────────┴─────────────┐
                                                       │  Customer host / container  │
                                                       │  Python SDK + SQLite WAL │
                                                       │  authorize → meter       │
                                                       └──────────────────────────┘
```

**Not production:** `apps/sync-api` (demo stub), `packages/mintry-node` (prototype), Go sidecar HTTPS MITM (scaffold).

---

## Prerequisites

- [ ] Supabase project
- [ ] Vercel account + GitHub repo access
- [ ] ES256 policy keypair (generate once; public on agents, private on Vercel only)
- [ ] Customer app where you can add `mintry.init()` (Python)

---

## 1. Supabase (control plane)

### 1.1 Tables

In **SQL Editor**, run:

```sql
CREATE TABLE IF NOT EXISTS policy_bundles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  version integer NOT NULL,
  policy_json jsonb NOT NULL,
  signature text NOT NULL,
  issued_at timestamptz DEFAULT now(),
  issued_by text,
  created_at timestamptz DEFAULT now(),
  UNIQUE(agent_id, version)
);

CREATE TABLE IF NOT EXISTS telemetry_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  mandate_id text NOT NULL,
  action text NOT NULL,
  amount numeric NOT NULL,
  details jsonb,
  recorded_at timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS policy_bundles_agent_version_idx
  ON policy_bundles (agent_id, version DESC);
```

### 1.2 RLS (recommended)

Agents and the dashboard often use the **service role** for policy reads/writes in v1.2 (anon + RLS commonly returns empty). If you tighten later:

- Service role: used only on the Vercel server (Sign & Push, fleet, summary enrichment).
- Never expose `MINTRY_SERVICE_ROLE_KEY` to the browser.

### 1.3 Auth (dashboard login)

1. **Authentication → Providers → Email** — enable Email (password and/or magic link).
2. **Authentication → URL configuration** — add redirect URLs:
   - `https://<your-vercel-domain>/auth/callback`
   - `http://localhost:3000/auth/callback` (local)
3. Create at least one user (Auth → Users), or allow sign-up if you intend to.

### 1.4 Keys to copy

| Supabase value | Env name(s) |
| --- | --- |
| Project URL | `MINTRY_CONTROL_PLANE_URL`, `NEXT_PUBLIC_SUPABASE_URL` |
| `anon` `public` key | `MINTRY_CONTROL_PLANE_KEY`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| `service_role` `secret` key | `MINTRY_SERVICE_ROLE_KEY` (**server only**) |

---

## 2. Policy keypair (ES256)

Generate once (never commit private key):

```bash
uv run python - <<'PY'
from mintry.core.crypto import generate_policy_keypair
pub, priv = generate_policy_keypair()
print(pub)
print(priv)
PY
```

| Key | Where |
| --- | --- |
| **Private** | Vercel only → `MINTRY_POLICY_PRIVATE_KEY` |
| **Public** | Every agent → `MINTRY_POLICY_PUBLIC_KEY` |

For multiline PEM in Vercel, paste the full PEM including `BEGIN`/`END` lines (Vercel UI accepts newlines), or use `\n` escapes in `.env` files.

**Do not** set `MINTRY_ALLOW_MOCK_SIGNATURES=1` in production.

---

## 3. Vercel (dashboard)

### 3.1 Import the project

1. [vercel.com/new](https://vercel.com/new) → import `mintry-fabric`.
2. **Root Directory:** `apps/dashboard`
3. Framework: Next.js (auto). Build: `npm run build` (see `apps/dashboard/vercel.json`).

### 3.2 Environment variables

Set these in **Vercel → Project → Settings → Environment Variables** (Production + Preview as needed):

#### Required — Supabase + Auth

| Variable | Notes |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Same as project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon public key |
| `MINTRY_CONTROL_PLANE_URL` | Same URL (server routes) |
| `MINTRY_CONTROL_PLANE_KEY` | Anon key (fallback) |
| `MINTRY_SERVICE_ROLE_KEY` | Service role — **server only** |

#### Required — signing

| Variable | Notes |
| --- | --- |
| `MINTRY_POLICY_PRIVATE_KEY` | ES256 private PEM |
| `MINTRY_REQUIRE_POLICY_SIGNATURES` | `1` |

#### Required — auth gate

| Variable | Notes |
| --- | --- |
| `MINTRY_REQUIRE_AUTH` | `1` |
| `MINTRY_DASHBOARD_ADMIN_TOKEN` | Break-glass / CI Bearer (long random) |
| `MINTRY_DASHBOARD_ALLOWED_EMAILS` | Optional: `you@co.com,ops@co.com` |

#### Optional — local ledger BFF

The hosted Vercel UI authors **policies in Supabase**. Live spend KPIs need a reachable Python ledger API:

| Variable | Notes |
| --- | --- |
| `MINTRY_DASHBOARD_API_ORIGIN` | e.g. `https://ledger.yourcompany.com` or leave unset for policy-only cloud |
| `MINTRY_DASHBOARD_API_TOKEN` | Bearer expected by that Python API |

If no Python API is deployed, Sign & Push / Fleet / Org still work against Supabase; summary KPIs fall back / stay empty until an API origin is set.

#### Optional — proactive alerts (async, off agent hot path)

| Variable | Notes |
| --- | --- |
| `MINTRY_WEBHOOK_URL` | JSON webhook for threshold + digest events |
| `MINTRY_SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `MINTRY_RESEND_API_KEY` | Resend API key for email alerts |
| `MINTRY_ALERT_EMAIL_TO` | Alert recipient |
| `MINTRY_ALERT_EMAIL_FROM` | Sender address (Resend-verified domain) |
| `MINTRY_DIGEST_INTERVAL_SEC` | Weekly digest interval (default `604800`) |

Agents fire threshold webhooks at 80/95/100% utilization. Dashboard **Send test alert** calls the same channels.

#### Optional — Stripe budget top-up

| Variable | Notes |
| --- | --- |
| `STRIPE_WEBHOOK_SECRET` | Verify signatures on `POST /api/stripe/webhook` |

In Stripe Dashboard → Webhooks → add endpoint:

`https://<your-vercel-domain>/api/stripe/webhook`

Event: `checkout.session.completed`. Checkout Session metadata must include `mandate_id` (or `mintry_mandate_id`). Amount from `amount_total` (cents) is applied via Python `/api/topup`.

Requires `MINTRY_DASHBOARD_API_ORIGIN` + `MINTRY_DASHBOARD_API_TOKEN` when the ledger runs on a customer host.

#### Explicitly off in production

| Variable | Value |
| --- | --- |
| `MINTRY_ALLOW_MOCK_SIGNATURES` | unset / `0` |
| `MINTRY_LOCAL_GOVERNANCE` | unset / `0` (caps via Sign & Push only) |
| `MINTRY_DEMO_MODE` | `1` only if you want test mandate IDs hidden |

### 3.3 Deploy

```bash
# from apps/dashboard, or via Vercel Git integration on push to master
cd apps/dashboard && npx vercel --prod
```

After deploy:

1. Open `https://<project>.vercel.app/login`
2. Sign in with Supabase email/password (or magic link)
3. **Sign & Push** a policy for `default_agent` (or your `MINTRY_AGENT_ID`)
4. Confirm a new row in Supabase `policy_bundles`

### 3.4 Custom domain

Vercel → Domains → add domain → update Supabase Auth redirect URLs to match.

---

## 4. Agent / enforcement plane (Python)

On each customer process (VM, container, laptop):

```bash
pip install "mintry-fabric @ git+https://github.com/ZolileN/mintry-fabric.git"
# or: uv add git+https://github.com/ZolileN/mintry-fabric.git
```

```python
import mintry
from openai import OpenAI

mintry.init(
    api_key="mk_…",           # or MINTRY_API_KEY
    db_path="~/.mintry/vouchers.db",
)

client = OpenAI()
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "…"}],
    extra_headers={"X-Mintry-Mandate": "research_task"},
)
```

### Agent environment

| Variable | Required | Notes |
| --- | --- | --- |
| `MINTRY_API_KEY` | yes | Init gate |
| `MINTRY_CONTROL_PLANE_URL` | yes | Supabase URL |
| `MINTRY_CONTROL_PLANE_KEY` or `MINTRY_SERVICE_ROLE_KEY` | yes | Prefer service role for policy fetch if RLS blocks anon |
| `MINTRY_POLICY_PUBLIC_KEY` | yes | Verify signed bundles |
| `MINTRY_AGENT_ID` | recommended | Must match Sign & Push `agent_id` |
| `MINTRY_DB_PATH` | optional | Default `~/.mintry/vouchers.db` |

Governance changes: **Sign & Push in the Vercel dashboard** — no app code change. Caps apply within one poll interval (~15–30s).

### Optional local observability API

On a host that can see the same ledger file:

```bash
uv run mintry dashboard --db ~/.mintry/vouchers.db --host 127.0.0.1 --port 8000
```

Point Vercel `MINTRY_DASHBOARD_API_ORIGIN` at that origin (with TLS + `MINTRY_DASHBOARD_API_TOKEN`) if you want cloud UI KPIs from the ledger.

---

## 5. Production checklist

- [ ] Supabase tables created; Auth email enabled; redirect URLs set
- [ ] Vercel root = `apps/dashboard`; env vars set (no mock signatures)
- [ ] `/login` works; Sign & Push writes `policy_bundles`
- [ ] Agent has public key + `MINTRY_AGENT_ID`; poll applies new version
- [ ] Exhausted / denied mandate blocks LLM call **without** calling Supabase on that request
- [ ] Control plane kill → agent keeps last-known-good
- [ ] Admin token stored in a secrets manager (break-glass only)
- [ ] Service role key never in `NEXT_PUBLIC_*`

---

## 6. Smoke test (supported path)

```bash
# 1) After Sign & Push in the UI, confirm Supabase has the version
# 2) On the agent host:
uv run python - <<'PY'
import os, time, mintry
mintry.init(api_key=os.environ["MINTRY_API_KEY"])
# wait one poll
time.sleep(25)
from mintry import _global_engine as e
print(e.policy_cache.get_sync_status() if e and e.policy_cache else "no cache")
PY
```

Legacy Render `sync-api` curls are **not** the production control plane — ignore them for go-live.

---

## 7. Docker / single-host (optional)

Shared volume for app + local dashboard API (not a substitute for Vercel control plane):

See root `docker-compose.yml`. Mount the same path for `vouchers.db`. WAL allows concurrent readers/writers on one host.

---

## 8. Kubernetes notes

- **Do not** put SQLite on NFS/EFS for multi-writer pods.
- Per-pod `emptyDir` ledger + **Option A** fleet partitions (static per-agent caps) is the supported multi-pod budget model.
- Go `mintry-proxy` sidecar: see `apps/sidecar/deploy/k8s-sidecar.yaml` — **HTTP scaffold**; HTTPS MITM not production-ready.

---

## 9. Security reminders

| Topic | Rule |
| --- | --- |
| Hot path | No HTTP to Mintry/Supabase inside authorize |
| Signatures | Real ES256 only in production |
| Auth | Supabase Auth for humans; admin token for break-glass; API token for Next→Python |
| Secrets | Alias-only in dashboard; provider keys stay on customer env/Vault |
| Local upsert | Disabled when CP configured unless `MINTRY_LOCAL_GOVERNANCE=1` |

See [SECURITY.md](../SECURITY.md), [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md), [RELEASE_NOTES_v1.2.0.md](./RELEASE_NOTES_v1.2.0.md).

---

## Quick reference — env by plane

| Plane | Key vars |
| --- | --- |
| **Vercel** | `NEXT_PUBLIC_SUPABASE_*`, `MINTRY_SERVICE_ROLE_KEY`, `MINTRY_POLICY_PRIVATE_KEY`, `MINTRY_REQUIRE_AUTH=1`, `MINTRY_DASHBOARD_ADMIN_TOKEN` |
| **Agent** | `MINTRY_API_KEY`, `MINTRY_CONTROL_PLANE_URL`, `MINTRY_POLICY_PUBLIC_KEY`, `MINTRY_AGENT_ID`, service/anon key for poll |
| **Local Python API** | `MINTRY_DB_PATH`, `MINTRY_DASHBOARD_API_TOKEN`, bind `127.0.0.1` or TLS at edge |
