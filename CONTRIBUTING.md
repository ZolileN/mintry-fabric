# Contributing to Mintry Fabric

Thank you for your interest in contributing to **Mintry Fabric**. This guide covers everything you need to go from zero to a merged pull request.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Environment Setup](#environment-setup)
3. [Project Structure](#project-structure)
4. [Branching Strategy](#branching-strategy)
5. [Making Changes](#making-changes)
6. [Running Tests](#running-tests)
7. [Submitting a Pull Request](#submitting-a-pull-request)
8. [Commit Message Format](#commit-message-format)
9. [Coding Standards](#coding-standards)

---

## Code of Conduct

Be respectful and professional. We are a small, focused team building infrastructure for the agentic economy. Harassment, dismissiveness, or disrespectful reviews will not be tolerated.

---

## Environment Setup

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.14+ (free-threaded / No-GIL build) |
| uv | Latest |
| OS | Ubuntu Linux (primary) |

### Steps

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/mintry-fabric.git
cd mintry-fabric

# 2. Install all dependencies including dev extras
uv sync --all-extras --dev

# 3. Verify your setup by running the test suite
uv run pytest -s tests/test_metering.py
```

If the metering test prints `[SUCCESS] Logic Fabric Metered the exact token cost.` — you are ready.

---

## Project Structure

```
mintry-fabric/
├── src/mintry/
│   ├── __init__.py          # Public entry point: mintry.init()
│   ├── core/
│   │   ├── wallet.py        # MintryWallet — SQLite ledger
│   │   └── engine.py        # PolicyEngine — authorization gatekeeper
│   ├── interceptors/
│   │   └── global_http.py   # GlobalHTTPInterceptor — HTTPX transport patch
│   ├── models/
│   │   └── mandates.py      # AP2IntentMandate — Pydantic data model
│   └── bridge/
│       └── stripe_mpp.py    # MppBridge — Stripe top-up integration
├── tests/
│   ├── test_metering.py
│   ├── test_mintry_fabric.py
│   ├── test_intent_fabric.py
│   └── test_mpp_bridge.py
├── docs/
│   ├── DEVELOPER_GUIDE.md
│   ├── API_REFERENCE.md
│   ├── CONFIGURATION.md
│   ├── TROUBLESHOOTING.md
│   └── engineering/
│       └── PR_REVIEW_STANDARD.md
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
├── pyproject.toml
└── README.md
```

---

## Branching Strategy

We use a simple trunk-based branching model.

| Branch | Purpose |
|---|---|
| `main` | Stable, always deployable |
| `feat/<short-description>` | New features |
| `fix/<short-description>` | Bug fixes |
| `docs/<short-description>` | Documentation only |
| `chore/<short-description>` | Tooling, CI, dependency updates |

**Never commit directly to `main`.** All changes go through a pull request.

---

## Making Changes

1. Create a branch from the latest `main`:
   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/async-transport-patch
   ```
2. Make your changes in `src/mintry/`.
3. Add or update tests in `tests/` to cover your change.
4. Ensure the surname in any documentation or code comments is spelled **Nonzapa**.
5. Run the full test suite before opening a PR (see below).

---

## Running Tests

```bash
# Run all tests
uv run pytest -s

# Run a specific test file
uv run pytest -s tests/test_metering.py

# Run with verbose output
uv run pytest -v
```

All tests must pass before a PR is submitted. If your change intentionally breaks an existing test, document why in the PR description.

---

## Submitting a Pull Request

1. Push your branch to your fork:
   ```bash
   git push origin feat/async-transport-patch
   ```
2. Open a PR against `ZolileN/mintry-fabric:main`.
3. Fill in the PR template — every section matters.
4. Link the relevant issue or task.
5. Add screenshots or test output for any behaviour change.
6. Request review from at least one team member.

Refer to [`docs/engineering/PR_REVIEW_STANDARD.md`](docs/engineering/PR_REVIEW_STANDARD.md) for full review criteria and approval rules.

---

## Commit Message Format

Use conventional commits for clarity in the changelog:

```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`

**Examples:**

```
feat(interceptor): add async httpx.AsyncClient transport patch
fix(wallet): import Decimal in add_funds method
docs(api): add PolicyEngine.authorize reference
chore(deps): bump pytest-httpx to 0.37.0
```

---

## Coding Standards

- **Type hints** are required on all public functions and methods.
- **Docstrings** are required on all public classes and methods.
- Keep functions small and single-purpose.
- Do not commit secrets, API keys, or database files.
- SQLite transactions that modify `spent_usd` must be atomic — never break the ledger invariant.
- Surname in all docs and comments: **Nonzapa** (not Nonzapa, not Nozapa).
