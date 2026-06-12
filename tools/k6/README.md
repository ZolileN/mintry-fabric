# tools/k6/README.md

# Mintry Fabric — k6 Load Test Suite

Performance validation scripts for the Mintry proxy. Designed to find the
10,000 RPS ceiling with sub-millisecond overhead measurement.

## Prerequisites

```bash
# Install k6
go install go.k6.io/k6@latest

# Verify
k6 version
```

## Test Topology

```
k6 VUs ──► Mintry Proxy :8000 ──► Gemini Mock Server :9090
                │
                └──► Prometheus metrics :9091/metrics
```

## Scripts

| Script | Purpose | Duration |
|--------|---------|----------|
| `mintry-baseline.js` | Ramp to 10k RPS, hunt the ceiling | ~7 min |
| `mintry-direct-vs-proxy.js` | Measure exact proxy overhead (direct vs proxy) | ~2.5 min |
| `mintry-mandate-stress.js` | Enforce budget under 200 concurrent VUs | 60s |

## Quick Start

### 1. Start Prerequisites

```bash
# Terminal 1 — upstream mock (deterministic 10ms baseline)
./tools/gemini-mock-server/gemini-mock

# Terminal 2 — Mintry with OTel
MINTRY_OTEL_ENABLED=1 uv run mintry dashboard \
  --db test_data/local.db --host 127.0.0.1 --port 8000
```

### 2. Run via orchestration script

```bash
# Smoke test (50 RPS, 60s)
bash tools/k6/run-load-test.sh --smoke

# Direct vs Proxy overhead measurement (~2.5 min)
bash tools/k6/run-load-test.sh --compare

# Full 10k RPS ceiling hunt (~7 min) with kernel tuning
bash tools/k6/run-load-test.sh --tune --full

# Mandate enforcement stress test
bash tools/k6/run-load-test.sh --mandate-stress
```

### 3. Or run k6 directly

```bash
# Smoke test
k6 run --env SMOKE=true tools/k6/mintry-baseline.js

# Full ceiling hunt
k6 run --env TARGET_RPS=10000 tools/k6/mintry-baseline.js

# Measure proxy overhead directly
k6 run tools/k6/mintry-direct-vs-proxy.js
```

## Understanding the Results

### The Two Latency Numbers

| Number | What it includes | Source |
|--------|-----------------|--------|
| k6 `http_req_duration` P99 | k6 TCP + Mintry pre-flight + upstream latency + Mintry post-flight + response transfer | k6 stdout |
| `mintry_proxy_duration_ms` P99 | Mintry pre-flight + upstream latency + Mintry post-flight (no k6 TCP stack) | `http://localhost:9091/metrics` |

**Proxy overhead** = `mintry_proxy_duration_ms` P99 − mock server's own 10ms baseline

The mock server logs show `duration=10.Xms` per request — that's your upstream
reference. Everything above it in `mintry_proxy_duration_ms` is Mintry's
pre+post-flight processing time. On this hardware, target is **< 1ms**.

### Stage Progression (baseline script)

```
Stage 1: 0 → 500 RPS     (30s)   warm up, establish connection pools
Stage 2: 500 RPS          (60s)   stable baseline — P99 should be ~12ms
Stage 3: 500 → 2,000 RPS  (60s)   medium load
Stage 4: 2,000 RPS        (60s)   hold — watch for P99 drift
Stage 5: 2,000 → 5,000    (60s)   high load — first sign of saturation here
Stage 6: 5,000 → 10,000   (120s)  ceiling hunt
Stage 7: → 0              (30s)   teardown
```

### Thresholds

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| `http_req_duration` P95 | < 50ms | 95% of requests complete fast |
| `http_req_duration` P99 | < 100ms | Tail latency ceiling |
| `mintry_success_rate` | > 99% | Error rate under 1% |

## Results Location

All runs write JSON summaries to `tools/k6/results/`:

```
tools/k6/results/
├── latest-run.json          # Full baseline run metrics
├── comparison-run.json      # Direct vs proxy comparison
├── mandate-stress.json      # Mandate enforcement results
├── pre-run-*.txt            # Prometheus snapshot before run
└── post-run-*.txt           # Prometheus snapshot after run
```

## Kernel Tuning (Before 10k RPS)

```bash
# See what will change
bash scripts/tune-kernel.sh --dry-run

# Apply (required for 10k RPS — prevents port exhaustion and FD limits)
sudo bash scripts/tune-kernel.sh
```
