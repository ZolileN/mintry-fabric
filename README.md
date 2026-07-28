# Mintry Fabric

Python enforcement plane for LLM spend governance. Hook once with `mintry.init()`,
author caps centrally as signed policy versions, enforce locally against a SQLite
ledger — **no control-plane network I/O on allow/block**.

## Supported path (production)

| Layer | What |
| --- | --- |
| Enforcement | Python SDK (`httpx` intercept) + local SQLite WAL |
| Control plane | Vercel dashboard + Supabase `policy_bundles` |
| Authoring | **Sign & Push** (and Fleet/Org compile → Sign & Push) |

```python
import mintry
from openai import OpenAI

mintry.init(api_key="mk_…", db_path="~/.mintry/vouchers.db")

client = OpenAI()
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Summarize these logs."}],
    extra_headers={"X-Mintry-Mandate": "research_task"},
)
```

Governance changes (new caps, deny, fleet partitions) are signed in the dashboard
and applied on the next poll. Application code does not change.

## What this is not (yet)

- **Go sidecar** (`apps/sidecar`) — scaffold; HTTP metering works; HTTPS MITM TBD
- **Node SDK** (`packages/mintry-node`) — prototype / private `0.1.0`
- **Local “Issue Mandate”** — opt-in only when a control plane is configured
  (`MINTRY_LOCAL_GOVERNANCE=1`); otherwise caps are authored via Sign & Push

## Install

```bash
uv sync --dev
# or
uv add git+https://github.com/ZolileN/mintry-fabric.git
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (Six Principles) and
[docs/PHASE2_PLAN.md](docs/PHASE2_PLAN.md). Current release: **v1.2.0**.

## CLI

```bash
uv run mintry mandates list
uv run mintry mandates inspect mt_task_882x
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
