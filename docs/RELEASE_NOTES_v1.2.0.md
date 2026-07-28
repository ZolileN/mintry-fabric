# Release Notes — Mintry Fabric v1.2.0

**Supabase Auth UI** for the control-plane dashboard.

## What's new

- `/login` — email/password and magic link via Supabase Auth
- Middleware refreshes sessions; production UI redirects unauthenticated users to `/login`
- Mutating APIs accept Supabase session (`issued_by` = email) or admin token break-glass
- Optional `MINTRY_DASHBOARD_ALLOWED_EMAILS`
- Nav session badge + Sign out

## Setup

1. Enable Email auth in Supabase; add redirect `https://<your-host>/auth/callback`
2. Set `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` on the dashboard
3. Optional: `MINTRY_REQUIRE_AUTH=1`, `MINTRY_DASHBOARD_ALLOWED_EMAILS=…`
4. Keep `MINTRY_DASHBOARD_ADMIN_TOKEN` for break-glass / CI

Auth stays on the dashboard control plane only — never on the LLM authorize hot path.
