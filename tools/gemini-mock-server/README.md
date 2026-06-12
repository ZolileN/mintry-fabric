# Gemini Mock Server

A minimal Go HTTP server that mimics the upstream Google Gemini API with a **deterministic 10 ms synthetic delay**. This is the control baseline for Mintry Fabric latency measurements — any recorded latency above 10 ms is pure proxy overhead.

## Quick Start

```bash
# From repo root
go run tools/gemini-mock-server/main.go

# Custom address
go run tools/gemini-mock-server/main.go -addr :9091

# Build binary
cd tools/gemini-mock-server
go build -o gemini-mock .
./gemini-mock
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1beta/models/<model>:generateContent` | Gemini content generation (10 ms delay) |
| `GET`  | `/health` | Health check, no delay |

## Smoke Test

```bash
# Health check
curl http://localhost:9090/health

# Gemini endpoint
curl -s -w "\nTotal time: %{time_total}s\n" \
  -X POST http://localhost:9090/v1beta/models/gemini-2.0-flash:generateContent \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"role": "user", "parts": [{"text": "Hello, mock!"}]}]
  }'
```

Expected: JSON response in ~10 ms. Any additional time is Mintry proxy overhead.

## Reading the Logs

```
[MOCK] req=1  path=/v1beta/models/gemini-2.0-flash:generateContent  status=200  duration=10.312ms
```

The `duration` field is wall-clock from request received to response flushed, **including** the 10 ms sleep. This is your upstream reference point.

## Using with Mintry + OpenTelemetry

1. Start this server: `go run tools/gemini-mock-server/main.go`
2. Point Mintry's test client at `http://localhost:9090`
3. Start Mintry with `MINTRY_OTEL_ENABLED=1`
4. Scrape `http://localhost:9091/metrics` for `mintry_proxy_duration_ms`

The delta between Mintry's internal span duration and this server's 10 ms baseline is your **exact proxy overhead**.
