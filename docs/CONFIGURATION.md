# Mintry Fabric: Configuration Reference

This document covers all environment variables, runtime settings, and file paths that control Mintry Fabric's behaviour.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MINTRY_API_KEY` | ✅ | — | Authentication key issued during onboarding. Passed to `mintry.init()`. |
| `MINTRY_DB_PATH` | ❌ | `~/.mintry/vouchers.db` | Override the default SQLite ledger path. |
| `MINTRY_LOG_LEVEL` | ❌ | `INFO` | Controls verbosity. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### Setting Variables

Use a `.env` file at your project root (never committed to version control):

```bash
# .env
MINTRY_API_KEY=mk_live_xxxxxxxxxxxxx
MINTRY_DB_PATH=/var/data/mintry/vouchers.db
```

Load via `python-dotenv` or export in your shell:

```bash
export MINTRY_API_KEY=mk_live_xxxxxxxxxxxxx
uv run python your_agent.py
```

---

## Runtime Configuration

### Default Database Path

```
~/.mintry/vouchers.db
```

The directory is created automatically on first run. To override:

```python
from mintry.core.wallet import MintryWallet

wallet = MintryWallet(db_path="/custom/path/vouchers.db")
```

### SQLite Pragmas

Mintry sets the following SQLite pragmas automatically on every connection:

| Pragma | Value | Reason |
|---|---|---|
| `journal_mode` | `WAL` | Write-Ahead Logging for concurrent reads and atomic writes. |
| `isolation_level` | `None` | Auto-commit mode; individual SQL statements are their own transactions. |

---

## Seed Mandate

On first initialization, the wallet inserts a seed mandate for testing and development:

| Field | Value |
|---|---|
| `id` | `mt_task_882x` |
| `max_usd` | `0.01` |
| `spent_usd` | `0.0` |
| `status` | `active` |

Inserted with `INSERT OR IGNORE` — will not overwrite existing data.

> **Note:** In production, replace this with real mandates. Do not rely on the seed mandate for production spend tracking.

---

## Intent Filter Configuration

The `GlobalHTTPInterceptor` contains a hardcoded list of prohibited prompt patterns:

```python
prohibited = [
    "bypass wallet",
    "disable mintry",
    "delete vouchers.db"
]
```

Matched against the lowercased concatenation of all message content. A configurable blocklist is planned for a future release.

---

## Token Pricing

The cost per token used in post-flight metering is currently hardcoded:

```python
actual_cost = (prompt_tokens + completion_tokens) * 0.000005
```

This approximates GPT-4o pricing. Configurable per-model pricing is planned for a future release.

---

## Security Configuration

- Restrict the database file to the owning user:
  ```bash
  chmod 600 ~/.mintry/vouchers.db
  ```
- Never set `MINTRY_API_KEY` in source code — always use environment variables or a secret manager.

---

## Recommended `.gitignore` Entries

```gitignore
.env
*.db
*.db-wal
*.db-shm
.mintry/
```
