# Mintry Fabric Deployment Guide

Mintry Fabric is designed around a local-first philosophy using SQLite. Because it relies on SQLite's Write-Ahead Logging (WAL) for high-concurrency access, deployment strategies require careful consideration of filesystem mounts and process topography.

## 1. Local Native Development

The simplest deployment model is running Mintry Fabric directly on your local workstation.

- **Storage**: `~/.mintry/vouchers.db`
- **Application**: Runs natively via Python SDK (`mintry.init()`) or Node.js SDK.
- **Dashboard**: Run via the CLI `mintry-dashboard` command.
- **Concurrency**: WAL mode allows the dashboard, CLI, and SDKs to read/write concurrently without locking.

## 2. Docker / Single-Host Deployments

When packaging your application inside Docker, you must mount a shared volume so the SDK and the observability dashboard can communicate via the same SQLite ledger.

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
    image: python:3.12-slim
    command: ["pip", "install", "mintry-fabric", "&&", "mintry-dashboard"]
    ports:
      - "8820:8820"
    volumes:
      - mintry-data:/root/.mintry

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
