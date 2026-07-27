# AGENTS.md

Mintry Fabric is a Python interception layer for LLM spend governance (see `README.md`, `docs/ARCHITECTURE.md`). Before making changes, follow the Six Architecture Principles in `.cursorrules` / `docs/ARCHITECTURE.md`.

## Cursor Cloud specific instructions

The startup update script already installs/refreshes dependencies (`uv sync --dev` for the Python package, `npm install` in `apps/dashboard`). uv is on `PATH` for interactive shells via `~/.bashrc`. The notes below are non-obvious gotchas; standard commands live in `README.md` and `docs/RUN_LOCAL.md`.

### Services & how to run them
- Python SDK / CLI / dashboard data API (the product core, `src/mintry`): run with `uv run ...`. Start the dashboard data API with `uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000`. This is a threaded `http.server` on port 8000, not a networked shared service — it serves the local SQLite ledger.
- Next.js dashboard UI (`apps/dashboard`, port 3000): `npm run dev`. It proxies the Python API via `MINTRY_DASHBOARD_API_ORIGIN` (default `http://127.0.0.1:8000`), so start the Python API first.
- Optional (not needed for the core product): Express `sync-api` (`apps/sync-api`, :8080), Node SDK (`packages/mintry-node`), Go Gemini mock (`tools/gemini-mock-server`, :9090), k6 load tests. `sync-api` and `mintry-node` already ship with committed `node_modules`.

### Non-obvious gotchas
- Python is the **free-threaded (No-GIL) 3.14 build**, pinned by `.python-version` (`3.14+freethreaded`). `uv sync` auto-downloads and uses it — do not force a regular CPython build.
- **Open the dashboard UI at `http://localhost:3000`, NOT `http://127.0.0.1:3000`.** Next.js 16 blocks cross-origin dev assets (`/_next/...`) for hosts not in `allowedDevOrigins`; loading via `127.0.0.1` silently prevents the client bundle from loading, so React never hydrates — the page shows all-zero KPIs / an empty ledger and forms do a native GET submit instead of calling the API. (`docs/RUN_LOCAL.md` says `127.0.0.1`; prefer `localhost`.)
- The dashboard `GET /api/summary` route (`apps/dashboard/src/app/api/summary/route.ts`) makes a Supabase (control plane) `policy_bundles` query. When the control plane is unreachable/unconfigured (no egress), that call blocks ~7s before the route falls back to local ledger data. Local data still returns. To avoid the delay, point `MINTRY_CONTROL_PLANE_URL` at a fast-responding/reachable endpoint (a listening host that returns quickly works), otherwise expect a ~7s first-load and wait for it rather than refreshing repeatedly.
- `MintryWallet` (`src/mintry/core/wallet.py`) is a **per-process singleton with an in-memory cache warmed at startup and asynchronous DB writes**. Do NOT mutate the SQLite ledger with external scripts (e.g. `scripts/seed_demo_environment.py`) while `mintry dashboard` is running — the process cache and the DB file diverge, and mandate upserts can take the UPDATE branch and update 0 rows (event logged, no row persisted). Seed the DB first, then start the dashboard; if you re-seed, restart the dashboard so cache == DB.
- To seed demo data for the dashboard: `uv run python scripts/seed_demo_environment.py --db test_data/local.db` (then start/restart the dashboard). `test_data/local.db` is tracked in git — avoid committing seeded/demo changes to it.

### Testing / lint status (pre-existing, not env issues)
- `uv run pytest`: the large majority of tests pass. A few fail under the free-threaded build due to async-worker timing races (the metering queue and telemetry batcher daemon threads, e.g. `test_metering.py::test_real_time_metering`, `test_telemetry_batch.py`). Real-world metering works — verified end-to-end via `httpx.MockTransport` (spend is recorded to the ledger). Treat these as flaky/timing tests, not setup breakage.
- `npm run lint` in `apps/dashboard` reports one pre-existing error (`@typescript-eslint/no-explicit-any` in `src/app/api/summary/route.ts`).
