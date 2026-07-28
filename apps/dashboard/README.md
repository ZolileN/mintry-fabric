# Mintry Dashboard

Next.js App Router UI for spend observability and policy administration.

## Run locally

1. Start the Python API: `uv run mintry dashboard --db test_data/local.db --host 127.0.0.1 --port 8000`
2. `npm install && npm run dev`
3. Open **http://localhost:3000** (not `127.0.0.1` — see `AGENTS.md`)

## Auth (Supabase Auth UI)

Primary: **Supabase email/password or magic link** at `/login`.

```bash
# apps/dashboard/.env.local (or root .env loaded by Next)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
# optional:
# MINTRY_DASHBOARD_ALLOWED_EMAILS=you@company.com
# MINTRY_REQUIRE_AUTH=1
```

In the Supabase dashboard: Authentication → enable Email provider; add redirect URL
`http://localhost:3000/auth/callback` (and your production origin).

Break-glass: admin token via the **Admin token** tab on `/login`, or
`POST /api/login` with `{ "token": "…" }`, or `Authorization: Bearer …`.

Forward machine auth to Python with `MINTRY_DASHBOARD_API_TOKEN` (never put user JWTs on the LLM hot path).

## Policy signing

Uses canonical ES256 (`src/lib/policy-crypto.ts`) with `MINTRY_POLICY_PRIVATE_KEY`. Mock signatures require explicit `MINTRY_ALLOW_MOCK_SIGNATURES=1` and are rejected when signatures are required.
