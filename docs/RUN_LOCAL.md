# Mintry Fabric: Run Locally

This guide is based on the current repository contents in `src/mintry`.

## Prerequisites

- Python `3.14+` to match `pyproject.toml`
- `uv`

## Setup

```bash
cd /home/zolile/Documents/mintry-fabric
uv sync --dev
source .venv/bin/activate
```

If you prefer not to activate the virtualenv, use `uv run ...` for all commands below.

## Verify the Package Imports

```bash
uv run python -c "import mintry; print('mintry import ok')"
```

## Start the Dashboard

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
```

Expected output:

```text
✨ Mintry Observability Dashboard running at http://127.0.0.1:8000
```

The dashboard will create the SQLite DB if it does not already exist.

## Use the CLI

In another terminal:

```bash
uv run mintry --db test_data/local.db mandates list
uv run mintry --db test_data/local.db mandates inspect mt_task_882x
```

## Minimal SDK Smoke Test

```python
import mintry

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

engine.wallet.create_mandate("smoke_task", 1.00)
print(engine.wallet.get_mandate("smoke_task"))
```

Run it:

```bash
uv run python smoke_test.py
```

## Run Tests

```bash
uv run pytest
```

Focused runs:

```bash
uv run pytest tests/test_metering.py
uv run pytest tests/test_dynamic_mandate.py
uv run pytest tests/test_observability.py
```

## Useful Local Paths

- default database: `~/.mintry/vouchers.db`
- recommended local dev database: `test_data/local.db`

## Notes

- the dashboard uses Python’s built-in HTTP server
- the current implementation is designed around a local SQLite ledger, not a networked shared service
- there is no Docker packaging in the repo yet

## Common Fixes

### `ModuleNotFoundError: mintry`

Install the package into the environment:

```bash
uv sync --dev
```

### `ModuleNotFoundError: openai`

Runtime dependencies are missing from the active environment:

```bash
uv sync --dev
```

### `unable to open database file`

Use a writable path:

```bash
mkdir -p test_data
uv run mintry dashboard --db test_data/local.db
```
