# Mintry Fabric API Reference

This document describes the current Python API implemented in `src/mintry`.

## Top-Level API

### `mintry.init(api_key, db_path="~/.mintry/vouchers.db", webhook_url=None)`

Initialize the wallet, engine, and global HTTPX interceptor.

Parameters:

| Name | Type | Description |
|---|---|---|
| `api_key` | `str` | Required non-empty string. Stored on the engine instance for integration use. |
| `db_path` | `str` | SQLite ledger path. Defaults to `~/.mintry/vouchers.db`. |
| `webhook_url` | `str | None` | Optional webhook endpoint for authorization-failure and shield-exhaustion events. |

Returns:

- `PolicyEngine`

Raises:

- `ValueError` if `api_key` is empty or not a string

Side effects:

- creates the SQLite ledger if needed
- installs sync and async HTTPX patches once per process
- prints startup messages unless `MINTRY_JSON_LOGS=1`

## `MintryWallet`

```python
from mintry.core.wallet import MintryWallet
```

### `MintryWallet(db_path="~/.mintry/vouchers.db")`

Opens the SQLite ledger, creates schema if missing, enables WAL mode, and seeds the default mandate `mt_task_882x`.

### `get_audit_log(mandate_id) -> list[dict]`

Returns append-only history rows with:

- `id`
- `timestamp`
- `action`
- `amount`
- `details`

### `check_authorization(mandate_id, cost=0.002) -> bool`

Legacy wallet-level authorization helper. Checks headroom and records the provided cost immediately if allowed.

### `add_funds(mandate_id, amount) -> bool`

Increases `max_usd` for an existing mandate and records a `top_up` audit event. `amount` is intended to be a `Decimal`, but any value convertible to `float` will work.

### `get_mandate(mandate_id) -> dict`

Returns:

| Key | Description |
|---|---|
| `budget_usd` | Budget ceiling for the mandate |
| `spent_usd` | Recorded spend |
| `status` | `active`, `exhausted`, `expired`, or `unknown` |
| `expires_at` | `datetime` or `None` |

Unknown mandates return zeroed values with `status="unknown"`.

### `record_usage(mandate_id, actual_cost) -> None`

Adds actual post-flight spend and logs a `spend` event.

### `get_spent(mandate_id) -> float`

Returns the current `spent_usd` for a mandate.

### `create_mandate(mandate_id, max_usd, expires_at=None) -> None`

Creates a mandate row and emits a `create` audit event.

### `update_mandate(mandate_id, max_usd, expires_at=None, status="active") -> None`

Updates budget, status, and expiry. Used by the dashboard allocation flow.

### `exhaust_mandate(mandate_id) -> None`

Marks the mandate as `exhausted` and logs an `exhaust` event.

### `is_expired(mandate_id) -> bool`

Checks expiry and automatically updates an active expired mandate to `status="expired"` with a matching audit event.

### `list_mandates() -> list[dict]`

Returns all mandates ordered by ID with budget, spend, status, and expiry values.

## `PolicyEngine`

```python
from mintry.core.engine import PolicyEngine, Mandate
```

### `PolicyEngine(wallet, webhook_url=None)`

Parameters:

| Name | Type | Description |
|---|---|---|
| `wallet` | `MintryWallet` | Backing ledger instance |
| `webhook_url` | `str | None` | Optional explicit webhook URL. Falls back to `MINTRY_WEBHOOK_URL` if unset. |

### `authorize(mandate_id, request, deduct=True) -> bool`

Authorization flow:

1. reject expired mandates
2. reject `exhausted` mandates
3. require at least `$0.01` remaining headroom
4. optionally deduct a flat `0.002` pre-flight fee when `deduct=True`

Returns `True` when the request may proceed and `False` when it should be blocked.

### `get_budget_summary(mandate_id) -> dict`

Returns a structured summary with:

- `mandate_id`
- `budget_usd`
- `spent_usd`
- `remaining_usd`
- `status`
- `expired`

### `shield(task, max_usd=None, expires_at=None)`

Context manager for two modes:

- shared-mandate mode: if `max_usd` is `None` and `task` already exists as a mandate ID, the existing mandate is reused and remains active on exit
- ephemeral mode: if `max_usd` is provided, a new `mt_<12 hex chars>` mandate is created and marked exhausted on exit

If `max_usd` is `None` and no existing mandate matches `task`, the engine creates a shared named mandate with a default budget of `0.05`.

Yields a `Mandate` object with:

- `id`
- `task`
- `max_usd`

When an ephemeral shield exits, the engine also emits a `mandate_exhausted` webhook event if webhooks are configured.

## `GlobalHTTPInterceptor`

```python
from mintry.interceptors.global_http import GlobalHTTPInterceptor
```

### `GlobalHTTPInterceptor(engine)`

Wraps a `PolicyEngine` for global HTTPX interception.

### `install() -> None`

Monkey-patches:

- `httpx.Client.send`
- `httpx.AsyncClient.send`

Only requests to known LLM hosts are intercepted:

- `api.openai.com`
- `api.anthropic.com`
- `generativelanguage.googleapis.com`
- `api.mistral.ai`

For intercepted requests, Mintry:

1. resolves the mandate ID from `X-Mintry-Mandate` or falls back to `mt_task_882x`
2. runs engine authorization without a pre-flight deduction
3. blocks prohibited prompt patterns
4. forwards the original request
5. reads usage data from successful responses
6. calculates cost using `mintry.core.pricing.calculate_cost()`
7. records spend in the wallet

### `_reset() -> None`

Testing helper that restores the original HTTPX send methods and clears install state.

## Pricing Helpers

```python
from mintry.core.pricing import calculate_cost, get_model_rates, register_model, list_models
```

### `calculate_cost(model, prompt_tokens, completion_tokens) -> float`

Calculates spend using model-specific input and output rates.

### `get_model_rates(model) -> dict[str, float]`

Returns `{"input": ..., "output": ...}` for a model. Uses exact match first, then prefix matching for versioned names, then a default fallback rate.

### `register_model(model, input_rate, output_rate) -> None`

Adds or overrides a model entry at runtime.

### `list_models() -> list[str]`

Lists all registered models.

## Signed Mandates

```python
from mintry.models.mandates import AP2IntentMandate, sign_mandate
```

### `AP2IntentMandate`

Fields:

- `mandate_id`
- `user_id`
- `max_budget`
- `currency`
- `resource_scope`
- `expires_at`
- `signature`

Methods:

- `is_expired() -> bool`
- `get_signing_payload() -> bytes`
- `verify_signature(public_key) -> bool`

### `sign_mandate(mandate, private_key) -> str`

Returns a base64-encoded ES256 signature for the canonical mandate payload.
