# Mintry Dashboard

Next.js App Router UI for local spend observability and policy administration.

## Run locally

1. Start the Python API: `uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000`
2. `npm install && npm run dev`
3. Open **http://localhost:3000** (not `127.0.0.1` — see `AGENTS.md`)

## Auth

Set `MINTRY_DASHBOARD_ADMIN_TOKEN` for mutating routes. Log in via `POST /api/login` with `{ "token": "..." }` (httpOnly cookie) or send `Authorization: Bearer …`.

Forward the same (or separate) token to Python with `MINTRY_DASHBOARD_API_TOKEN`.

## Policy signing

Uses canonical ES256 (`src/lib/policy-crypto.ts`) with `MINTRY_POLICY_PRIVATE_KEY`. Mock signatures require explicit `MINTRY_ALLOW_MOCK_SIGNATURES=1` and are rejected when signatures are required.
