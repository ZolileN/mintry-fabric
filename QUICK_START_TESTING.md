# Dashboard and Shared-Ledger Quick Start

This guide walks through the dashboard-driven mandate flow using the code as it exists today.

## Prerequisites

- Python `3.14+`
- `uv`

## 1. Install Dependencies

```bash
cd /home/zolile/Documents/mintry-fabric
uv sync --dev
```

## 2. Start the Dashboard

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## 3. Create a Mandate in the UI

In the dashboard:

1. enter a mandate ID such as `test_job_001`
2. set a budget, for example `50`
3. optionally set an ISO date/time expiry
4. apply the mandate

You should see the mandate appear in the ledger and audit feed.

## 4. Reuse That Mandate from Python

Create `sdk_demo.py`:

```python
import mintry

engine = mintry.init(
    api_key="mk_dev_example",
    db_path="test_data/local.db",
)

with engine.shield("test_job_001") as mandate:
    print(mandate)
    print(engine.authorize(mandate.id, None, deduct=False))
```

Run it:

```bash
uv run python sdk_demo.py
```

Because the mandate already exists, `shield("test_job_001")` reuses it instead of creating a temporary one.

## 5. Write Metered Spend Into the Same DB

The repo includes a small example:

```bash
PYTHONPATH=src python3 tests/test_allocated_budget_usage.py --db test_data/local.db
```

If the dashboard is open against that same DB path, it will refresh and show the updated spend automatically.

## 6. Revoke the Mandate

Use the dashboard’s revoke control for `test_job_001`, then rerun the Python example. Authorization should now fail.

## 7. Optional Verification

```bash
uv run pytest tests/test_observability.py
uv run pytest tests/test_allocated_budget_usage.py
```
