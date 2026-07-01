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

## Start the Dashboard API

The Next.js dashboard uses the Python runtime as its local ledger API.

```bash
uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
```

Expected output:

```text
✨ Mintry Observability Dashboard running at http://127.0.0.1:8000
```

## Start the Next.js Dashboard UI

In a second terminal:

```bash
cd apps/dashboard
npm run dev
```

Then open `http://127.0.0.1:3000`.

The dashboard will create the SQLite DB if it does not already exist through the Python API layer.

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

engine.wallet.create_mandate("smoke_task", 100.00)
print(engine.wallet.get_mandate("smoke_task"))
```

Run it:

```bash
uv run python smoke_test.py
```

### Check Spent Budget

After running requests through the engine, inspect the `spent_usd` field to confirm budget has been consumed:

```python
import mintry

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

engine.wallet.create_mandate("smoke_task", 100.00)
print(engine.wallet.get_mandate("smoke_task"))
# {'budget_usd': 100.0, 'spent_usd': 0.0, 'status': 'active', 'expires_at': None}

# ... make metered API calls through the engine ...

# Re-fetch to see updated spend
mandate = engine.wallet.get_mandate("smoke_task")
print(f"Spent: ${mandate['spent_usd']:.4f} / ${mandate['budget_usd']:.2f}")
```

Expected output after metered usage:

```text
✨ Mintry Logic Fabric Hooked into HTTPX (sync + async)
✨ Mintry Logic Fabric Active | No-GIL: True
{'budget_usd': 100.0, 'spent_usd': 0.0, 'status': 'active', 'expires_at': None}
Spent: $0.0200 / $100.00
```

> **Note:** `spent_usd` updates automatically whenever the engine proxies a metered request. The value persists across process restarts via the local SQLite ledger at `test_data/local.db`.

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

- the dashboard UI is the Next.js app in `apps/dashboard`
- the dashboard data API still uses Python’s built-in HTTP server
- the current implementation is designed around a local SQLite ledger, not a networked shared service
- the root Docker image serves the Next.js dashboard on port `3000`

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

---

## Performance Baseline Testing (Acquisition Roadmap)

Use these steps to isolate and measure Mintry's internal proxy overhead using the local Gemini mock server and OpenTelemetry instrumentation.

### Step 1 — Start the Gemini Mock Server

The mock server accepts standard Gemini API payloads and returns a deterministic response after exactly **10 ms**. Any latency above 10 ms during your tests is pure Mintry proxy overhead.

```bash
# From repo root
go run tools/gemini-mock-server/main.go
# Listens on http://localhost:9090
```

Smoke-test it:

```bash
curl -s -w "\nTotal time: %{time_total}s\n" \
  -X POST http://localhost:9090/v1beta/models/gemini-2.0-flash:generateContent \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"role": "user", "parts": [{"text": "hello"}]}]}'
```

Expected: JSON response in ~10 ms. Check `/health` for server status:

```bash
curl http://localhost:9090/health
```

### Step 2 — Start Mintry with OpenTelemetry Enabled

In a second terminal:

```bash
MINTRY_OTEL_ENABLED=1 uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000
```

Expected output includes:

```text
✨ Mintry Logic Fabric Active | No-GIL: True
📊 Mintry metrics: http://localhost:9091/metrics
```

### Step 3 — Verify the Prometheus Metrics Endpoint

```bash
curl http://localhost:9091/metrics | grep mintry
```

Key metrics to watch:

| Metric | Description |
|--------|-------------|
| `mintry_proxy_duration_ms_bucket` | Internal proxy latency histogram |
| `mintry_proxy_duration_ms_count` | Total proxied requests |
| `mintry_proxy_cost_usd_bucket` | Per-request LLM spend histogram |

### Step 4 — (Optional) Enable Console Span Output

```bash
MINTRY_OTEL_ENABLED=1 MINTRY_OTEL_CONSOLE_SPANS=1 uv run mintry dashboard --db test_data/local.db
```

This prints each span to stdout for manual inspection.

### Step 5 — Apply Kernel Tuning Before Load Testing

Before running `k6` at 10,000 RPS, apply OS-level socket optimisations:

```bash
# Preview what will run (no changes applied)
bash scripts/tune-kernel.sh --dry-run

# Apply (requires root)
sudo bash scripts/tune-kernel.sh
```

Settings applied:

| Setting | Value | Rationale |
|---------|-------|-----------|
| `ulimit -n` | 65535 | One file descriptor per concurrent socket |
| `net.ipv4.ip_local_port_range` | 1024–65535 | Prevents port exhaustion at high churn |
| `net.ipv4.tcp_tw_reuse` | 1 | Recycles TIME_WAIT sockets immediately |

To make sysctl changes persist across reboots:

```bash
echo 'net.ipv4.ip_local_port_range=1024 65535' | sudo tee -a /etc/sysctl.d/99-mintry-perf.conf
echo 'net.ipv4.tcp_tw_reuse=1'                 | sudo tee -a /etc/sysctl.d/99-mintry-perf.conf
sudo sysctl --system
```

### Live Mock Server Tests

Once the Go mock server is running, the live integration tests in the telemetry suite activate automatically:

```bash
uv run pytest tests/test_telemetry.py -v
# TestMockServerIntegration tests will run (not skipped)
```

These assert:
- Mock server responds in ≥ 10 ms
- Mintry's proxy overhead above the 10 ms baseline is < 5 ms
