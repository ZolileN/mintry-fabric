# Mintry Fabric: Configuration Reference

This document describes configuration that is actually implemented in the current codebase.

## Function Parameters

The main runtime configuration is passed directly to `mintry.init()`:

```python
engine = mintry.init(
    api_key="mk_dev_example",
    db_path="test_data/local.db",
    webhook_url="https://example.com/mintry-webhook",
)
```

Parameters:

| Name | Default | Description |
|---|---|---|
| `api_key` | none | Required non-empty string |
| `db_path` | `~/.mintry/vouchers.db` | SQLite ledger location |
| `webhook_url` | `None` | Explicit webhook destination |

## Environment Variables

These variables are read by the current implementation:

| Variable | Default | Description |
|---|---|---|
| `MINTRY_JSON_LOGS` | unset | When set to `1`, startup and event logs are emitted as JSON |
| `MINTRY_WEBHOOK_URL` | unset | Fallback webhook URL used by `PolicyEngine` when `webhook_url` is not passed directly |

Notes:

- `MINTRY_API_KEY` is not auto-read by the library today; your application must pass `api_key` to `mintry.init()`
- `MINTRY_DB_PATH` is not currently consumed by the codebase

## SQLite Behaviour

`MintryWallet` currently:

- expands `~` in the configured DB path
- creates parent directories automatically
- opens a connection with `isolation_level=None`
- enables `PRAGMA journal_mode=WAL`

Schema:

- `mandates`
- `mandate_audit_log`

The wallet also seeds the default mandate `mt_task_882x`.

## Intent Filter

The interceptor blocks requests whose concatenated message text contains any of these lowercased phrases:

- `bypass wallet`
- `disable mintry`
- `delete vouchers.db`

This list is hardcoded today.

## Pricing Configuration

Built-in pricing lives in `src/mintry/core/pricing.py`.

You can extend it at runtime:

```python
from mintry.core.pricing import register_model

register_model("ft:gpt-4o-custom", input_rate=0.00001, output_rate=0.00003)
```

Lookup behaviour:

1. exact model match
2. prefix match for versioned names
3. fallback default rate

## File Permissions

Recommended local protections:

```bash
chmod 700 ~/.mintry
chmod 600 ~/.mintry/vouchers.db
```

## Suggested `.gitignore`

```gitignore
.env
*.db
*.db-wal
*.db-shm
.mintry/
```
