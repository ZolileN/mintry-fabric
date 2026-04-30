# Mintry Fabric: API Reference

This document describes the complete public interface of the `mintry` package.

---

## Top-Level

### `mintry.init(api_key)`

Initializes the Mintry Logic Fabric and installs the global HTTPX transport hook.

Must be called once at application startup, before any LLM client is instantiated.

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `api_key` | `str` | ✅ | Your `MINTRY_API_KEY` from the Mintry monitoring plane. |

**Returns**

`PolicyEngine` — The active engine instance. Use this to interact with the wallet and authorize mandates programmatically.

**Side Effects**

- Monkey-patches `httpx.Client.send` globally.
- Initializes `MintryWallet` and creates `~/.mintry/vouchers.db` if it does not exist.
- Prints confirmation to stdout.

**Example**

```python
import mintry

engine = mintry.init(api_key="mk_live_xxxxx")
# ✨ Mintry Logic Fabric Active | No-GIL: True
# ✨ Mintry Logic Fabric Hooked into HTTPX
```

**Raises**

Does not raise on initialization. Budget enforcement errors are raised at request time (see `PolicyEngine.authorize`).

---

## `MintryWallet`

Manages the local SQLite ledger (`vouchers.db`) for mandate tracking and spend attribution.

```python
from mintry.core.wallet import MintryWallet
```

### `MintryWallet(db_path="~/.mintry/vouchers.db")`

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `db_path` | `str` | `"~/.mintry/vouchers.db"` | Path to the SQLite database. Created automatically if it does not exist. |

**Notes**
- WAL mode (`PRAGMA journal_mode=WAL`) is enabled on connection for thread-safe concurrent access.
- A seed mandate (`mt_task_882x`, `max_usd=0.01`) is inserted on first run via `INSERT OR IGNORE`.

---

### `MintryWallet.check_authorization(mandate_id, cost=0.002)`

Checks whether a mandate has sufficient remaining budget and atomically deducts the cost if it does.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `mandate_id` | `str` | — | The unique mandate identifier. |
| `cost` | `float` | `0.002` | The estimated cost in USD to deduct if authorized. |

**Returns**

`bool` — `True` if the mandate had sufficient funds and the cost was deducted. `False` if the mandate does not exist or the budget is insufficient.

---

### `MintryWallet.record_usage(mandate_id, actual_cost)`

Adds actual post-flight token cost to the mandate's cumulative `spent_usd`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mandate_id` | `str` | The mandate to record spend against. |
| `actual_cost` | `float` | The exact USD cost calculated from token usage. |

**Notes**

This is called by `GlobalHTTPInterceptor` after every successful LLM response. It is the single source of truth for spend attribution.

---

### `MintryWallet.add_funds(mandate_id, amount)`

Increases the `max_usd` budget ceiling for an existing mandate (top-up).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mandate_id` | `str` | The mandate to increase budget for. |
| `amount` | `Decimal` | The amount in USD to add to `max_usd`. |

**Returns**

`bool` — `True` on success, `False` on failure (with error printed to stdout).

---

### `MintryWallet.get_mandate(mandate_id)`

Fetches the current budget and spend state for a mandate.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mandate_id` | `str` | The mandate to query. |

**Returns**

`dict` with the following keys:

| Key | Type | Description |
|---|---|---|
| `budget_usd` | `float` | The maximum allocated budget (`max_usd`). |
| `spent_usd` | `float` | Cumulative spend to date. |

Returns `{"budget_usd": 0.0, "spent_usd": 0.0}` if the mandate does not exist.

---

### `MintryWallet.get_spent(mandate_id)`

Returns the raw `spent_usd` value for a mandate.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mandate_id` | `str` | The mandate to query. |

**Returns**

`float` — Cumulative spend in USD. Returns `0.0` if the mandate does not exist.

---

## `PolicyEngine`

The authorization gatekeeper. Evaluates whether an outbound LLM request is permitted based on the remaining mandate budget.

```python
from mintry.core.engine import PolicyEngine
```

### `PolicyEngine(wallet)`

**Parameters**

| Name | Type | Description |
|---|---|---|
| `wallet` | `MintryWallet` | The wallet instance to query for authorization decisions. |

---

### `PolicyEngine.authorize(mandate_id, request, deduct=True)`

Performs a two-phase budget check for an outbound request.

**Phase 1 — Safety threshold:** Ensures at least `$0.01` of headroom remains (`budget_usd - spent_usd >= 0.01`).  
**Phase 2 — Base fee deduction:** If `deduct=True`, records a `$0.002` base fee via `wallet.record_usage`.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `mandate_id` | `str` | — | The mandate to authorize against. |
| `request` | `httpx.Request` | — | The outbound request (used for future request-level policies). |
| `deduct` | `bool` | `True` | Whether to apply the base fee deduction. Set to `False` when metering tokens post-flight instead. |

**Returns**

`bool` — `True` if authorized, `False` if budget is exhausted.

---

### `PolicyEngine.shield(task, max_usd)`

A context manager that creates a scoped mandate for a single task.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `task` | `str` | A human-readable task description. |
| `max_usd` | `float` | The budget ceiling for this task scope. |

**Returns**

A context manager that yields a mandate object with an `.id` attribute.

**Example**

```python
with engine.shield("analyze-logs", max_usd=0.10) as mandate:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Summarize these logs."}],
        extra_headers={"X-Mintry-Mandate": mandate.id}
    )
```

---

## `GlobalHTTPInterceptor`

Patches `httpx.Client.send` globally to intercept all LLM traffic.

```python
from mintry.interceptors.global_http import GlobalHTTPInterceptor
```

### `GlobalHTTPInterceptor(engine)`

**Parameters**

| Name | Type | Description |
|---|---|---|
| `engine` | `PolicyEngine` | The engine instance used for pre-flight authorization. |

---

### `GlobalHTTPInterceptor.install()`

Installs the global transport patch. Called automatically by `mintry.init()`.

After installation, every `httpx.Client.send` call is intercepted. The three-phase lifecycle:

1. **Pre-flight:** `PolicyEngine.authorize` is called with `deduct=False`.
2. **Flight:** The original request is forwarded to the LLM provider.
3. **Post-flight:** Token usage is extracted from the response and `wallet.record_usage` is called with the exact cost.

**Cost Calculation**

```
actual_cost = (prompt_tokens + completion_tokens) × $0.000005
```

**Raises**

`PermissionError` — Raised locally (before the network request) if:
- The mandate budget is exhausted.
- A prohibited intent pattern is detected in the prompt.

---

### `GlobalHTTPInterceptor.sync_intercept(request)`

Performs manual interception on a single request. Useful for testing.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `request` | `httpx.Request` | The request to inspect. |

**Raises**

`PermissionError` — If budget is exhausted or prohibited intent is detected.

---

## `AP2IntentMandate`

A Pydantic model representing an AP2-compliant signed mandate payload.

```python
from mintry.models.mandates import AP2IntentMandate
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mandate_id` | `str` | ✅ | Unique mandate identifier. |
| `user_id` | `str` | ✅ | The user or agent this mandate is issued to. |
| `max_budget` | `float` | ✅ | Maximum USD budget for the task cycle. |
| `currency` | `str` | `"USD"` | Currency denomination. |
| `resource_scope` | `list[str]` | `["inference", "search", "vector_db"]` | Resource types this mandate covers. |
| `expires_at` | `datetime` | ✅ | Mandate expiry timestamp. |
| `signature` | `str` | ✅ | BBS+ or ES256 cryptographic signature. |

---

## Error Reference

| Error | Raised By | Meaning |
|---|---|---|
| `PermissionError` | `GlobalHTTPInterceptor` | Budget exhausted or prohibited intent detected. The request was killed before reaching the provider. |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MINTRY_API_KEY` | ✅ | Authentication key for the Mintry monitoring plane. Passed to `mintry.init()`. |

See [`docs/CONFIGURATION.md`](CONFIGURATION.md) for full configuration reference.
