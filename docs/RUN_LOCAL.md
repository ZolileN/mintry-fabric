# Mintry Fabric: Run Locally

This guide is based on the current repository structure and code paths in `src/mintry`. It is focused on getting the platform running locally for development, dashboard testing, and SDK smoke tests.

## What This Platform Is

Mintry Fabric is a Python package that:

- creates a local SQLite ledger for mandates and spend tracking
- exposes a CLI via `mintry`
- can start a local dashboard server
- can patch `httpx` globally through `mintry.init()` so LLM traffic is metered and budget-checked

The main local entry points are:

- `mintry dashboard`
- `mintry mandates list`
- `mintry mandates inspect <id>`
- a Python script that calls `mintry.init(...)`

## Before You Start

There is one important repo mismatch to know up front:

- `pyproject.toml` declares `requires-python = ">=3.14"`
- some older docs still mention Python `3.12+`

Use Python `3.14` if you want to match the package metadata exactly. If you are only running source locally, some flows may still work on Python `3.12`, but that is not the declared target for the package.

## Step 1: Move Into the Repository

```bash
cd /home/zolile/Documents/mintry-fabric
```

## Step 2: Install `uv` If You Do Not Already Have It

This repo is already set up for `uv`.

```bash
uv --version
```

If that fails, install `uv` first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 3: Create or Select the Right Python Version

Preferred:

```bash
uv python install 3.14
uv venv --python 3.14
```

If you already have a compatible interpreter, `uv` can reuse it.

## Step 4: Sync Dependencies

Install the package and development dependencies:

```bash
uv sync --dev
```

This is the safest local setup because tests import `mintry` as an installed package. Running `pytest` without installation can fail with `ModuleNotFoundError: mintry`.

## Step 5: Activate the Virtual Environment

```bash
source .venv/bin/activate
```

You can also skip activation and prefix commands with `uv run`.

## Step 6: Confirm the Package Imports

```bash
uv run python -c "import mintry; print('mintry import ok')"
```

Expected result:

```text
mintry import ok
```

## Step 7: Start the Local Dashboard

The fastest visible way to run the platform locally is the dashboard:

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
```

Expected console output:

```text
✨ Mintry Observability Dashboard running at http://127.0.0.1:8000
```

Then open:

```text
http://127.0.0.1:8000
```

What this does:

- creates the SQLite database if it does not exist
- creates the `mandates` and `mandate_audit_log` tables
- seeds a default mandate `mt_task_882x`
- serves the dashboard UI and JSON API locally

## Step 8: Inspect the Local Ledger From the CLI

In a second terminal:

```bash
source .venv/bin/activate
uv run mintry --db test_data/local.db mandates list
```

To inspect one mandate:

```bash
uv run mintry --db test_data/local.db mandates inspect mt_task_882x
```

This confirms the CLI can read the same database the dashboard is using.

## Step 9: Run a Minimal SDK Smoke Test

Create a local smoke script:

```python
import mintry

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

print(engine.wallet.get_mandate("mt_task_882x"))
```

Run it:

```bash
uv run python smoke_test.py
```

Expected output includes:

```text
✨ Mintry Logic Fabric Hooked into HTTPX (sync + async)
✨ Mintry Logic Fabric Active | No-GIL: True
```

This confirms:

- the wallet initializes
- the SQLite ledger is available
- the global `httpx` interceptor is installed

## Step 10: Run Tests

Run the full suite:

```bash
uv run pytest
```

If you want a smaller verification pass first:

```bash
uv run pytest tests/test_metering.py tests/test_observability.py
```

If tests fail with missing imports, it usually means dependencies were not synced yet. Run:

```bash
uv sync --dev
```

## Step 11: Optional Manual Dashboard Flow

Once the dashboard is open:

1. Create a new mandate in the allocation form.
2. Confirm it appears in the ledger table.
3. Revoke it and confirm the status changes.
4. Inspect the audit feed to confirm create, update, and revoke events.

For a longer walkthrough, see [QUICK_START_TESTING.md](../QUICK_START_TESTING.md).

## Local File and Runtime Notes

- Default database path: `~/.mintry/vouchers.db`
- Recommended local dev database: `test_data/local.db`
- Dashboard host default: `127.0.0.1`
- Dashboard port default: `8000`
- The local dashboard is implemented with Python’s built-in HTTP server, not FastAPI or Flask

## Troubleshooting

### `ModuleNotFoundError: mintry`

Cause:

- the package is not installed into the local environment yet

Fix:

```bash
uv sync --dev
```

### `ModuleNotFoundError: openai`

Cause:

- runtime dependencies are not installed in the active environment

Fix:

```bash
uv sync --dev
```

### `unable to open database file`

Cause:

- the selected database path is not writable

Fix:

```bash
mkdir -p test_data
uv run mintry dashboard --db test_data/local.db
```

### Port `8000` is already in use

Use a different port:

```bash
uv run mintry dashboard --db test_data/local.db --port 8001
```

## Recommended Local Workflow

If you just want the shortest reliable path:

1. `uv sync --dev`
2. `source .venv/bin/activate`
3. `uv run mintry dashboard --db test_data/local.db`
4. open `http://127.0.0.1:8000`
5. `uv run mintry --db test_data/local.db mandates list`
6. `uv run pytest`
