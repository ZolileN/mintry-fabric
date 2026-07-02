# Mintry Fabric: Developer Guide

Mintry Fabric is a local governance layer for LLM traffic. It intercepts supported provider requests at the `httpx` transport layer and ties them to named mandates in a SQLite ledger.

## End-to-End Flow

### 1. Initialize the Fabric

```python
import mintry

engine = mintry.init(
    api_key="mk_dev_example",
    db_path="test_data/local.db",
)
```

This creates:

- a `MintryWallet`
- a `PolicyEngine`
- a global sync and async HTTPX interceptor

### 2. Create or Reuse a Mandate

Explicit creation:

```python
engine.wallet.create_mandate("research_task", 2.00)
```

Scoped ephemeral mandate:

```python
with engine.shield("log-analysis", max_usd=0.50) as mandate:
    ...
```

Shared named mandate reuse:

```python
with engine.shield("research_task") as mandate:
    assert mandate.id == "research_task"
```

### 3. Send a Request

```python
from openai import OpenAI

client = OpenAI(api_key="sk-example")
client.chat.completions.create(
    model="gpt-5-preview",
    messages=[{"role": "user", "content": "Summarize the incident."}],
    extra_headers={"X-Mintry-Mandate": "research_task"},
)
```

### 4. What Mintry Does

- checks expiry and budget headroom
- rejects exhausted mandates
- blocks a small set of prohibited prompt phrases
- forwards the request to the provider
- reads usage metadata from the response
- calculates spend from the pricing table
- updates SQLite and the audit log

## Main Components

### `MintryWallet`

Ledger responsibilities:

- initialize schema
- seed the default mandate
- create, update, exhaust, and inspect mandates
- write audit log entries

### `PolicyEngine`

Policy responsibilities:

- expiry enforcement
- budget authorization
- webhook dispatch
- shared versus ephemeral shield behaviour

### `GlobalHTTPInterceptor`

Transport responsibilities:

- patch sync and async HTTPX clients
- detect supported LLM hosts
- resolve mandate IDs from headers
- run pre-flight policy checks
- meter successful responses

## Supported Providers

- OpenAI
- Anthropic
- Google Gemini
- Mistral

Support is host-based and depends on those SDKs or clients ultimately using `httpx`.

## Dashboard Workflow

The local dashboard and the SDK can point at the same SQLite file.

Typical flow:

1. start the dashboard with `mintry dashboard --db test_data/local.db`
2. allocate or revoke mandates from the browser
3. run an SDK script against the same `--db` path
4. watch spend and audit updates appear in the dashboard

## Design Constraints

- **Adherence to the [Six Architecture Principles](ARCHITECTURE.md) is mandatory for all development.**
- the interceptor is a process-wide monkey-patch
- the ledger is local SQLite, not a hosted control plane
- multi-process and network-shared deployments are not yet a packaged product path
- webhook support exists, but remote sync is still only represented by local hooks and integration points
- **Zero latency**: the enforcement plane (local SQLite) must operate synchronously without adding network hops to the critical path.

## Recommended Development Loop

```bash
uv sync --dev
uv run pytest
uv run mintry dashboard --db test_data/local.db
```
