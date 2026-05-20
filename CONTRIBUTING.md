# Contributing to Mintry Fabric

## Setup

```bash
git clone https://github.com/<your-username>/mintry-fabric.git
cd mintry-fabric
uv sync --dev
```

Recommended verification:

```bash
uv run pytest
```

## Project Layout

```text
src/mintry/
  __init__.py
  bridge/
  core/
  interceptors/
  models/
tests/
docs/
```

## Working Agreement

- make changes against `main` using a branch
- add or update tests with behaviour changes
- keep public APIs typed and documented
- do not commit secrets or SQLite database files
- do not assume docs are accurate until you compare them against `src/mintry`

## Useful Commands

```bash
uv run pytest
uv run pytest tests/test_observability.py
uv run mintry mandates list
uv run mintry dashboard --db test_data/local.db
```

## Pull Requests

Please include:

- what changed
- how you verified it
- screenshots if the dashboard UI changed
- any remaining risks or follow-up work

See [docs/engineering/PR_REVIEW_STANDARD.md](docs/engineering/PR_REVIEW_STANDARD.md) for review expectations.
