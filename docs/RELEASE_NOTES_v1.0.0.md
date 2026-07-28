# Release Notes — Mintry Fabric v1.0.0

**Date:** 2026-07-28  
**Scope:** Phase 1 production gate (Python SDK + local ledger + Supabase control plane)

## Headline

Central governance now actually governs traffic: signed policy bundles are
verified locally, cached as last-known-good, and enforced on the `httpx`
interceptor hot path with **zero control-plane network I/O**.

## What’s in

- Canonical ES256 sign/verify (dashboard + Python)
- `PolicyEngine.authorize()` reads `PolicyCache` caps
- Dashboard admin token / login cookie; Python API bearer token
- Spend reservations under concurrency; `mintry.close()` flush
- Telemetry batching from `init()`
- Idempotent `init()` for the same ledger path
- Honest labeling of legacy `sync-api` and experimental `mintry-node`

## Upgrade notes

1. Set `MINTRY_POLICY_PUBLIC_KEY` on agents and `MINTRY_POLICY_PRIVATE_KEY` on the signer.
2. Set `MINTRY_DASHBOARD_ADMIN_TOKEN` / `MINTRY_DASHBOARD_API_TOKEN` for shared deployments.
3. Do **not** set `MINTRY_ALLOW_MOCK_SIGNATURES` in production.
4. Prefer Supabase as the control plane; treat `apps/sync-api` as demo-only.

## Out of scope (Phase 2)

Sidecar proxy, fleet-wide atomic budgets, org/project hierarchy, full Supabase Auth UI.

## Verify

```bash
uv run pytest tests/test_production_readiness.py tests/test_v1_dod.py -q
```
