# Mintry Fabric: Troubleshooting

## `PermissionError: Budget Exhausted`

Cause:

- the mandate has insufficient remaining headroom
- the mandate is already `exhausted`

Check state:

```python
mandate = engine.wallet.get_mandate("research_task")
print(mandate)
```

Top up if needed:

```python
from decimal import Decimal
engine.wallet.add_funds("research_task", Decimal("0.10"))
```

## `PermissionError` mentions expiry

Cause:

- the mandate’s `expires_at` has passed

Fix:

- create a new mandate
- or update the existing one through the dashboard or wallet API

## `PermissionError: Prohibited Intent Detected`

Cause:

- the request body contains one of the built-in blocked phrases

Current blocked phrases:

- `bypass wallet`
- `disable mintry`
- `delete vouchers.db`

## Requests are not being metered

Check the common causes:

1. `mintry.init()` was called after the client was created
2. the request is not going to a supported LLM host
3. dependencies were not installed into the environment you are running

Correct order:

```python
import mintry
from openai import OpenAI

engine = mintry.init(api_key="mk_dev_example")
client = OpenAI(api_key="sk-example")
```

## `ModuleNotFoundError: mintry`

The package is not installed in the active environment.

```bash
uv sync --dev
```

## `ModuleNotFoundError: openai`

Runtime dependencies are missing from the active environment.

```bash
uv sync --dev
```

## `sqlite3.OperationalError: unable to open database file`

Use a writable path and make sure the parent directory exists:

```bash
mkdir -p test_data
uv run mintry dashboard --db test_data/local.db
```

## `sqlite3.OperationalError: database is locked`

Mintry uses SQLite with WAL mode, which helps, but it is still not a substitute for a fully managed shared write service.

What to do:

- keep development flows on one machine and one DB path
- avoid heavy concurrent multi-process writers
- use the dashboard and SDK against the same local file only when that access pattern is modest

## Webhooks are not firing

Check:

1. `webhook_url` was passed to `mintry.init()` or `MINTRY_WEBHOOK_URL` is set
2. the target accepts POST requests
3. your code path actually triggers an authorization failure or shield exhaustion event

## Tests fail during collection

Most collection failures in this repo come from setup rather than logic:

```bash
uv sync --dev
uv run pytest
```

If you deliberately run raw `pytest` outside the synced environment, imports may fail.
