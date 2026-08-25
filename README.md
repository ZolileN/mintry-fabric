# Mintry Fabric

Python enforcement plane for LLM spend governance. Hook once with `mintry.init()`,
set budgets centrally as signed policies, enforce locally against SQLite — **no
control-plane network I/O on allow/block**.

**Current release: `v1.3.0`** (background-first governance).

## Supported path (production)

| Layer | What |
| --- | --- |
| Enforcement | Python SDK (`httpx` intercept) + local SQLite WAL |
| Control plane | Vercel dashboard + Supabase `policy_bundles` + `telemetry_events` |
| Authoring | Simple budget form or Sign & Push (Fleet/Org compile) |
| Alerts | Webhook / Slack / email at 80/95/100% + optional weekly digest |

```python
import mintry
from openai import OpenAI

mintry.init(api_key="mk_…", db_path="~/.mintry/vouchers.db")

with mintry.mandate("research_task", cap=50.0):
    client = OpenAI()
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Summarize these logs."}],
    )
    # attributed automatically — no per-request headers required
```

Governance changes (new caps, fleet partitions) are signed in the dashboard
and applied on the next poll. Application code does not change.

## What this is not (yet)

- **Go sidecar** (`apps/sidecar`) — scaffold; HTTP metering works; HTTPS MITM TBD
- **Node SDK** (`packages/mintry-node`) — prototype / private `0.1.0`
- **Local ledger edits** — opt-in when control plane configured (`MINTRY_LOCAL_GOVERNANCE=1`)

## Install

```bash
uv sync --dev
# or
uv add git+https://github.com/ZolileN/mintry-fabric.git
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (Six Principles) and
[docs/PHASE2_PLAN.md](docs/PHASE2_PLAN.md).

## CLI

```bash
uv run mintry mandates list
uv run mintry mandates inspect research_task
uv run mintry dashboard --db test_data/local.db
```

## Local dashboard

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
cd apps/dashboard && npm run dev
# open http://localhost:3000  (not 127.0.0.1)
```

## Production deploy

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Vercel dashboard + Supabase control plane + Python agents.

## License

See [LICENSE](LICENSE).
