# Mintry Fabric

Mintry Fabric is a Python interception layer for LLM spend governance. It hooks into `httpx`, checks mandates before requests leave the process, meters provider responses after they return, and writes budget and audit data to a local SQLite ledger.

The current repository state includes:

- sync and async `httpx` interception
- dynamic mandate routing via `X-Mintry-Mandate`
- per-model pricing for OpenAI, Anthropic, Gemini, and Mistral
- mandate expiry enforcement and audit logging
- a local CLI and observability dashboard
- webhook notifications and JSON log output

## Install

For local development:

```bash
uv sync --dev
```

For direct use from GitHub:

```bash
uv add git+https://github.com/ZolileN/mintry-fabric.git
```

## Quick Start

```python
import mintry
from openai import OpenAI

engine = mintry.init(
    api_key="mk_dev_example",
    db_path="test_data/local.db",
)

engine.wallet.create_mandate("research_task", 1.00)

client = OpenAI(api_key="sk-example")
response = client.chat.completions.create(
    model="gpt-5-preview",
    messages=[{"role": "user", "content": "Summarize these logs."}],
    extra_headers={"X-Mintry-Mandate": "research_task"},
)
```

If the request succeeds, Mintry will:

1. check that `research_task` still has budget
2. block prohibited prompt patterns before flight
3. read usage metadata from the response
4. record the actual spend in SQLite

## CLI

```bash
uv run mintry mandates list
uv run mintry mandates inspect mt_task_882x
uv run mintry dashboard --db test_data/local.db
```

The dashboard serves a local web UI at `http://127.0.0.1:8000` by default.

## Testing

The repo’s tests assume the package dependencies are installed into the active environment.

```bash
uv sync --dev
uv run pytest
```

Useful focused runs:

```bash
uv run pytest tests/test_metering.py
uv run pytest tests/test_observability.py
uv run pytest tests/test_sprint3.py
```

## Key Components

- `MintryWallet`: SQLite-backed mandate ledger and audit log
- `PolicyEngine`: authorization, expiry checks, shared-mandate reuse, webhook dispatch
- `GlobalHTTPInterceptor`: sync/async `httpx` monkey-patch and post-flight metering
- `AP2IntentMandate`: signed mandate model with ES256 verification helpers

## Architecture Guardrails

All features and contributions must strictly adhere to the [Six Architecture Principles](docs/ARCHITECTURE.md). Features that violate deterministic, local-first enforcement will not be accepted.

## Current Release Status

The codebase implements roadmap milestones through the `v0.5.0` feature set, and the package version reflects this. See [docs/ROADMAP.md](docs/ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md) for the current state and remaining work before `v1.0.0`.

## License

MIT
