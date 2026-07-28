# LEGACY / DEMO ONLY — NOT THE PRODUCTION CONTROL PLANE

This Express service is a **local/demo stub** retained for historical
prototyping. It stores mandates and spend in a JSON file under `/tmp` by
default, has **no authentication**, and does **not** distribute signed,
versioned policy bundles.

## Do not use in production

Production control plane topology (see `docs/ARCHITECTURE.md`):

```text
Next.js dashboard → Supabase policy_bundles → Python SDK poll → PolicyCache → enforce
```

## What this service still does

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/api/summary` | Aggregate from JSON store |
| POST | `/api/mandates/upsert` | In-place mutation |
| POST | `/api/mandates/revoke` | In-place mutation |
| POST | `/api/v1/sync` | Additive spend ingest (not WAL sync) |

## Run (demo only)

```bash
npm install
npm run build
npm start
```

Default port: `8080` (`PORT`). Store path: `MINTRY_SYNC_STORE_PATH`.
