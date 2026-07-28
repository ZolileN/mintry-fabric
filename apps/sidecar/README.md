# Mintry Proxy (Phase 2 sidecar) — ADR-003

**Status:** scaffold / not a drop-in HTTPS governance proxy yet.

Language-agnostic HTTP forward proxy that enforces Mintry budgets against the
local SQLite ledger (`vouchers.db`). The **supported production path** remains
the Python SDK + Sign & Push control plane.

## Principles

- **Enforce locally:** allow/block reads only the local ledger (no control-plane
  calls on the hot path).
- **Fail closed on unknown/exhausted mandates,** open only when headroom remains.
- Policy sync remains a separate concern (Python SDK / future sidecar poller).

## Quick start

```bash
cd apps/sidecar
go test ./...
go run ./cmd/mintry-proxy -db /path/to/vouchers.db -addr 127.0.0.1:8820
```

Point a client at the proxy (HTTP absolute-form, e.g. mock servers):

```bash
curl -x http://127.0.0.1:8820 \
  -H 'X-Mintry-Mandate: customer_support_agent' \
  http://127.0.0.1:9090/v1beta/models/gemini-2.0-flash:generateContent \
  -d '{"contents":[{"parts":[{"text":"hi"}]}]}'
```

Health: `GET http://127.0.0.1:8820/healthz`

## HTTPS note

`CONNECT` to LLM hosts returns `501` unless `MINTRY_ALLOW_UNINSPECTED_HTTPS=1`
(tunnel without metering). TLS MITM termination is a follow-up milestone.

## Docker

```bash
docker build -t mintry-proxy -f apps/sidecar/Dockerfile apps/sidecar
docker run --rm -p 8820:8820 -v mintry-data:/data \
  -e MINTRY_DB_PATH=/data/vouchers.db mintry-proxy
```

See `deploy/k8s-sidecar.yaml` for the Pod sidecar pattern.
