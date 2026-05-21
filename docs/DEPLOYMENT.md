# Mintry Fabric Deployment Guide

Mintry Fabric is designed around a local-first philosophy using SQLite. Because it relies on SQLite's Write-Ahead Logging (WAL) for high-concurrency access, deployment strategies require careful consideration of filesystem mounts and process topography.

## Architecture Map

Mintry Fabric utilizes a decoupled architecture separating the control and enforcement planes:

| Component | What it Runs | Where it Lives | Cost to You |
| --------- | ------------ | -------------- | ----------- |
| **Frontend** | Next.js Marketing & Dashboard | Vercel | $0 (Free Tier) |
| **Control Plane** | Central Sync API & Sync Database | Render | $0 to $5/mo |
| **Enforcement Plane** | Core Logic Fabric + Local SQLite Ledger | Customer's Infrastructure | $0 (Paid by client) |

The **Enforcement Plane** is what gets deployed to the client's infrastructure. It writes to a local SQLite ledger (`vouchers.db`) for zero-latency budget authorization. The **Control Plane** handles asynchronous syncing back to central servers.

## 1. Local Native Development

The simplest deployment model is running Mintry Fabric directly on your local workstation.

- **Storage**: `~/.mintry/vouchers.db`
- **Application**: Runs natively via Python SDK (`mintry.init()`) or Node.js SDK.
- **Dashboard UI**: Run the Next.js app from `apps/dashboard`.
- **Dashboard API**: Run via the CLI `mintry dashboard` command.
- **Concurrency**: WAL mode allows the dashboard, CLI, and SDKs to read/write concurrently without locking.

## 2. Docker / Single-Host Deployments

When packaging your application inside Docker, you must mount a shared volume so the SDK and the shipped Next.js dashboard runtime can communicate via the same SQLite ledger.

### `docker-compose.yml` Example

```yaml
version: '3.8'

services:
  app:
    build: .
    volumes:
      - mintry-data:/root/.mintry
    environment:
      - MINTRY_API_KEY=${MINTRY_API_KEY}
    
  dashboard:
    build: .
    ports:
      - "3000:3000"
    volumes:
      - mintry-data:/root/.mintry
    environment:
      - MINTRY_DB_PATH=/root/.mintry/vouchers.db

volumes:
  mintry-data:
```

> [!WARNING]
> Both containers must mount the same path (or at least map to the same file) for the wallet telemetry to sync.

## 3. Kubernetes and Multi-Host Deployments

### The SQLite NFS Problem
SQLite does not support concurrent writes across network file systems (NFS, EFS) reliably. **Do not put `vouchers.db` on an EFS mount** expecting multiple distinct application pods to share the ledger safely.

### Recommended Pattern: The Sidecar Proxy (Coming Soon)
For Kubernetes, the recommended pattern is the **Sidecar Proxy**. Rather than running SDK-level interception, you deploy the Mintry proxy as a sidecar container within your Pod.

1. **The Pod**: Contains your `app` container and the `mintry-proxy` container.
2. **The Ledger**: An `emptyDir` volume shared between the containers holds `vouchers.db` for the lifecycle of the Pod.
3. **Routing**: The `app` container sets `HTTP_PROXY=localhost:8820`.

*(Note: Centralized budget synchronization across multiple Pods requires an external remote-sync worker, which is on the roadmap but not available in v1.0.0).*

## 4. Production Security

- **Webhooks**: Always set `MINTRY_WEBHOOK_URL` in production to alert your observability stack when mandates are exhausted or intents are blocked.
- **Dashboard Access**: The Mintry dashboard currently does not feature built-in authentication. In production, place it behind an API Gateway or reverse proxy (like Nginx or Caddy) with Basic Auth or OIDC enabled.
- **JSON Logs**: Set `MINTRY_JSON_LOGS=1` so your log aggregators (Datadog, Splunk, Grafana Loki) can parse the `event: spend_metered` telemetry out of the box.

## 5. Live Production Smoke Test

After deploying the control plane to Render and the dashboard to Vercel, you can verify the full data path from your terminal by writing a temporary test mandate into the live sync API and checking that it appears on the production dashboard.

### Current Production Endpoints

- **Dashboard**: `https://mintry-fabric-dashboard.vercel.app`
- **Sync API**: `https://mintry-sync-api.onrender.com`

### 1. Create a Test Mandate

```bash
curl -X POST https://mintry-sync-api.onrender.com/api/mandates/upsert \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-prod-budget",
    "budget_usd": 25,
    "expires_at": null
  }'
```

Expected response:

```json
{"success":true}
```

### 2. Send Budget Usage

```bash
curl -X POST https://mintry-sync-api.onrender.com/api/v1/sync \
  -H "Content-Type: application/json" \
  -d '{
    "mandate_id": "test-prod-budget",
    "spend": 3.75,
    "tokens": 1200
  }'
```

Expected response shape:

```json
{"status":"synced","mandate_id":"test-prod-budget","mandate":{...}}
```

### 3. Verify the Backend Summary

```bash
curl https://mintry-sync-api.onrender.com/api/summary
```

You should see `test-prod-budget` in the `mandates` list, and the `stats.total_spent` value should reflect the recorded spend.

### 4. Verify the Dashboard

Open the production dashboard:

`https://mintry-fabric-dashboard.vercel.app`

The dashboard polls the backend every few seconds, so the new mandate and spend should appear shortly without a redeploy.

### 5. Clean Up the Test Data

```bash
curl -X POST https://mintry-sync-api.onrender.com/api/mandates/revoke \
  -H "Content-Type: application/json" \
  -d '{"id":"test-prod-budget"}'
```

Expected response:

```json
{"success":true}
```

### Notes

- Use obviously fake IDs such as `test-prod-budget` so test data is easy to identify and remove.
- This smoke test writes to the live production control plane, so it should be treated as production data even though it is temporary.
- The existing local test suite in [`tests/test_allocated_budget_usage.py`](/home/zolile/Documents/mintry-fabric/tests/test_allocated_budget_usage.py:74) validates local ledger behavior only; it does not push data into the deployed dashboard.
