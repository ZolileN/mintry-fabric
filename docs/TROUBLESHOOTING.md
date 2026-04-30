# Mintry Fabric: Troubleshooting Guide

Common errors, symptoms, and resolutions.

---

## 1. `PermissionError: Mintry Logic Fabric: Budget Exhausted`

**Symptom:** LLM calls raise a `PermissionError` locally before reaching the provider.

**Cause:** The mandate's `spent_usd` has reached or exceeded `max_usd`, or the safety threshold of `$0.01` headroom is not available.

**Resolution:**

```python
# Check remaining budget
spent = engine.wallet.get_spent("mt_task_882x")
mandate = engine.wallet.get_mandate("mt_task_882x")
remaining = mandate["budget_usd"] - spent
print(f"Remaining: ${remaining:.4f}")

# Top up the mandate if needed
from decimal import Decimal
engine.wallet.add_funds("mt_task_882x", Decimal("0.10"))
```

---

## 2. `PermissionError: Mintry Logic Fabric: Prohibited Intent Detected`

**Symptom:** A `PermissionError` is raised mentioning "Security Violation" before the request is sent.

**Cause:** The prompt contains one of the blocked patterns: `"bypass wallet"`, `"disable mintry"`, or `"delete vouchers.db"`.

**Resolution:** Review the prompt content being sent by your agent. These patterns indicate either a misconfigured prompt template or an adversarial injection attempt. Do not attempt to work around the filter — investigate the root cause.

---

## 3. The Fabric Does Not Intercept Requests

**Symptom:** LLM calls succeed but no spend is recorded in `vouchers.db`.

**Cause:** `mintry.init()` was not called before the `OpenAI` (or other) client was instantiated, OR an `httpx.AsyncClient` is being used instead of `httpx.Client`.

**Resolution:**

```python
# CORRECT: init before creating the client
import mintry
from openai import OpenAI

engine = mintry.init(api_key="your_key")  # Must come first
client = OpenAI()
```

> **Known limitation (v0.1.0):** Only `httpx.Client` (synchronous) is patched. Async clients using `httpx.AsyncClient` bypass the Fabric entirely. Use synchronous clients until async support is released.

---

## 4. SQLite `database is locked` Error

**Symptom:** `sqlite3.OperationalError: database is locked` appears during high-concurrency tests or multi-process runs.

**Cause:** WAL mode is enabled but multiple processes are attempting to write simultaneously without a timeout.

**Resolution:** WAL mode significantly reduces locking, but write contention can still occur. Ensure only one process writes to the ledger at a time, or configure a connection timeout:

```python
conn = sqlite3.connect(db_path, timeout=10)  # Wait up to 10 seconds
```

---

## 5. `add_funds` Raises `NameError: name 'Decimal' is not defined`

**Symptom:** Calling `wallet.add_funds()` raises a `NameError`.

**Cause:** Known bug in v0.1.0 — `Decimal` is referenced in `wallet.py` but not imported.

**Workaround:** Import `Decimal` and cast to `float` before calling:

```python
from decimal import Decimal
engine.wallet.add_funds("mt_task_882x", Decimal("0.05"))
```

A fix is tracked for v0.1.1.

---

## 6. Spend is Double-Counted

**Symptom:** `get_spent()` returns values higher than expected after a single request.

**Cause:** Both `check_authorization` (which deducts a base fee) and `record_usage` (which records the actual token cost) are being called on the same request. In `install()`, `authorize` is called with `deduct=False` to prevent this — but if `check_authorization` is called separately in the same flow, double-counting occurs.

**Resolution:** Use the interceptor's `install()` path exclusively. Do not call `check_authorization` manually if the global hook is already active.

---

## 7. `vouchers.db` Not Found / Permission Denied

**Symptom:** `sqlite3.OperationalError: unable to open database file` on startup.

**Cause:** The `~/.mintry/` directory cannot be created, or the user does not have write permission to the target path.

**Resolution:**

```bash
mkdir -p ~/.mintry
chmod 700 ~/.mintry
```

Or override the path to a writable location:

```python
wallet = MintryWallet(db_path="/tmp/mintry_dev.db")
```

---

## 8. Tests Fail with `pytest-httpx` Version Mismatch

**Symptom:** `ImportError` or fixture errors when running `uv run pytest`.

**Cause:** `pytest-httpx` has breaking API changes between minor versions. The project requires `>=0.36.2`.

**Resolution:**

```bash
uv sync --all-extras --dev
uv run pytest --version
```

Ensure the installed version matches the constraint in `pyproject.toml`.

---

## Getting Further Help

If your issue is not listed here:

1. Check the [API Reference](API_REFERENCE.md) to verify correct usage.
2. Check the [CHANGELOG](../CHANGELOG.md) for known issues in your version.
3. Open a GitHub issue with your Python version, `uv` version, error message, and a minimal reproduction script.
4. For security-related issues, follow the [SECURITY](../SECURITY.md) disclosure process instead.
