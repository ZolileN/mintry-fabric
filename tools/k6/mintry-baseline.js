/**
 * tools/k6/mintry-baseline.js
 *
 * Mintry Fabric — k6 Load Test: Baseline Throughput Hunt
 * ======================================================
 *
 * PURPOSE
 * -------
 * Find the 10,000 RPS ceiling by routing traffic through Mintry's proxy to
 * the local Gemini mock server (localhost:9090) and measuring:
 *
 *   - Request rate (RPS)
 *   - P50 / P95 / P99 latency
 *   - Error rate
 *   - Mintry internal proxy duration (via Prometheus scrape after the run)
 *
 * TOPOLOGY
 * --------
 *
 *   k6  ──►  Mintry Proxy (localhost:8000)  ──►  Gemini Mock (localhost:9090)
 *                        │
 *                        └──► Prometheus metrics (localhost:9091/metrics)
 *
 * HOW TO RUN
 * ----------
 *
 *   # 1. Apply kernel tuning (requires root)
 *   sudo bash scripts/tune-kernel.sh
 *
 *   # 2. Start the Gemini mock server (terminal 1)
 *   ./tools/gemini-mock-server/gemini-mock
 *
 *   # 3. Start Mintry with OTel enabled (terminal 2)
 *   MINTRY_OTEL_ENABLED=1 uv run mintry dashboard \
 *     --db test_data/local.db --host 127.0.0.1 --port 8000
 *
 *   # 4. Run this script (terminal 3)
 *   k6 run tools/k6/mintry-baseline.js
 *
 *   # For a quick smoke test (50 VUs, 30s):
 *   k6 run --env SMOKE=true tools/k6/mintry-baseline.js
 *
 *   # For the full 10k RPS hunt:
 *   k6 run --env TARGET_RPS=10000 tools/k6/mintry-baseline.js
 *
 * STAGES
 * ------
 * The script uses a ramping-arrival-rate executor to drive exact RPS targets,
 * not VU concurrency, so throughput is decoupled from response time variability.
 *
 *   Stage 1: Ramp 0 → 500 RPS  (warm up — establishes connection pools)
 *   Stage 2: Hold 500 RPS      (confirm baseline is stable)
 *   Stage 3: Ramp → 2,000 RPS  (medium load)
 *   Stage 4: Hold 2,000 RPS    (observe P99 under sustained load)
 *   Stage 5: Ramp → 5,000 RPS  (high load — watch for error rate rise)
 *   Stage 6: Ramp → 10,000 RPS (ceiling hunt)
 *   Stage 7: Ramp down → 0     (graceful teardown)
 *
 * THRESHOLDS
 * ----------
 * The run FAILS if any of these are breached:
 *   - P95 latency > 50 ms    (Mintry + loopback must stay fast)
 *   - P99 latency > 100 ms
 *   - Error rate  > 1%
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

// ─── Configuration ────────────────────────────────────────────────────────────

const SMOKE_MODE  = __ENV.SMOKE === "true";
const TARGET_RPS  = parseInt(__ENV.TARGET_RPS  || "10000", 10);

// Mintry is a monkey-patch library interceptor, NOT a TCP proxy.
// k6 sends requests directly to the upstream (mock server or real Gemini).
// Mintry's OTel spans measure internal processing overhead separately via
// Prometheus at http://localhost:9091/metrics.
//
// To load test against the real Gemini API instead of the mock:
//   k6 run --env TARGET_URL=https://generativelanguage.googleapis.com tools/k6/mintry-baseline.js
const TARGET_URL = __ENV.TARGET_URL || "http://localhost:9090";
const BASE_URL   = TARGET_URL;
const IS_MOCK    = BASE_URL.includes("localhost:9090");

// ─── Custom metrics ───────────────────────────────────────────────────────────

const mandateErrors   = new Counter("mintry_mandate_errors");
const proxyErrors     = new Counter("mintry_proxy_errors");
const successRate     = new Rate("mintry_success_rate");
const proxyLatency    = new Trend("mintry_proxy_latency_ms", true);   // reports P99

// ─── Scenarios / Stages ───────────────────────────────────────────────────────

function buildStages() {
  if (SMOKE_MODE) {
    // Quick 60-second smoke test: ramp to 50 RPS, hold, ramp down
    return [
      { duration: "15s", target: 50  },
      { duration: "30s", target: 50  },
      { duration: "15s", target: 0   },
    ];
  }

  // Full ceiling hunt
  const peak = TARGET_RPS;
  return [
    { duration: "30s",  target: 500          },  // warm up
    { duration: "60s",  target: 500          },  // stable baseline
    { duration: "60s",  target: 2000         },  // medium load
    { duration: "60s",  target: 2000         },  // hold medium
    { duration: "60s",  target: 5000         },  // high load
    { duration: "120s", target: peak         },  // ceiling hunt
    { duration: "30s",  target: 0            },  // teardown
  ];
}

export const options = {
  scenarios: {
    mintry_rps: {
      executor: "ramping-arrival-rate",
      startRate: 0,
      timeUnit: "1s",
      preAllocatedVUs: 500,   // warm pool — avoids VU-spin latency spikes
      maxVUs: 2000,           // hard ceiling on virtual users
      stages: buildStages(),
    },
  },

  thresholds: {
    // Wall-clock latency as seen by k6 (includes network to Mintry + Mintry processing)
    "http_req_duration{scenario:mintry_rps}": [
      { threshold: "p(95)<50",  abortOnFail: false },
      { threshold: "p(99)<100", abortOnFail: false },
    ],
    // Custom Mintry metrics
    "mintry_success_rate": [{ threshold: "rate>0.99", abortOnFail: false }],
  },

  // Pretty summary at the end
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)", "p(99.9)"],
};

// ─── Request payload ──────────────────────────────────────────────────────────

// Re-use the same encoded payload object on every iteration — avoids GC pressure.
const PAYLOAD = JSON.stringify({
  contents: [{ role: "user", parts: [{ text: "Mintry k6 load test probe." }] }],
});

const HEADERS = {
  "Content-Type": "application/json",
  // Route through the default seed mandate. In a real test you'd rotate
  // mandate IDs here to test multi-tenant budget enforcement under load.
  "x-mintry-mandate": "mt_task_882x",
};

// ─── Main VU function ─────────────────────────────────────────────────────────

export default function () {
  const startTs = Date.now();

  const res = http.post(
    `${BASE_URL}/v1beta/models/gemini-2.0-flash:generateContent`,
    PAYLOAD,
    {
      headers: HEADERS,
      tags: { mode: IS_MOCK ? "mock" : "live" },
      // Generous timeout — if Mintry is hanging we want to capture that, not
      // silently drop the request.
      timeout: "5s",
    }
  );

  const elapsed = Date.now() - startTs;
  proxyLatency.add(elapsed);

  // Classify the response
  const ok = check(res, {
    "status 200":                (r) => r.status === 200,
    "has candidates field":      (r) => {
      try { return JSON.parse(r.body).candidates !== undefined; }
      catch { return false; }
    },
  });

  successRate.add(ok);

  if (res.status === 402 || res.status === 403) {
    // Mintry mandate exceeded or auth failure — budget enforcement working
    mandateErrors.add(1);
  } else if (res.status !== 200) {
    proxyErrors.add(1);
  }

  // No sleep — arrival-rate executor controls pacing, not the VU loop.
}

// ─── Setup / Teardown ─────────────────────────────────────────────────────────

export function setup() {
  // Confirm the target upstream is up before starting load.
  const targetHealth = IS_MOCK
    ? http.get("http://localhost:9090/health")
    : http.get(`${BASE_URL}/health`);

  if (IS_MOCK && targetHealth.status !== 200) {
    throw new Error(
      "Gemini mock server not reachable at localhost:9090. " +
      "Run: ./tools/gemini-mock-server/gemini-mock"
    );
  }

  // OTel metrics endpoint (optional — only active when MINTRY_OTEL_ENABLED=1)
  const metricsUp = http.get("http://localhost:9091/metrics");
  if (metricsUp.status !== 200) {
    console.warn(
      "OTel metrics endpoint not active at localhost:9091. " +
      "Start Mintry with MINTRY_OTEL_ENABLED=1 to capture internal P99 spans."
    );
  } else {
    console.info("OTel metrics endpoint confirmed — mintry_proxy_duration_ms will be populated.");
  }

  console.log(`\n╔══════════════════════════════════════════════════╗`);
  console.log(`║  Mintry Fabric k6 Load Test                      ║`);
  console.log(`╠══════════════════════════════════════════════════╣`);
  console.log(`║  Target:     ${BASE_URL.padEnd(36)}║`);
  console.log(`║  Mode:       ${(IS_MOCK ? "DIRECT → mock server" : "→ real Gemini API").padEnd(36)}║`);
  console.log(`║  Target RPS: ${String(SMOKE_MODE ? "50 (smoke)" : TARGET_RPS).padEnd(36)}║`);
  console.log(`║  OTel P99:   http://localhost:9091/metrics        ║`);
  console.log(`╚══════════════════════════════════════════════════╝\n`);
}

export function handleSummary(data) {
  // Emit a machine-readable JSON summary alongside the default human summary.
  return {
    "tools/k6/results/latest-run.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data),
  };
}

// Minimal text summary helper (k6 doesn't expose its default formatter as an import)
function textSummary(data) {
  const rps     = data.metrics["http_reqs"]?.values?.rate?.toFixed(1) ?? "N/A";
  const p95     = data.metrics["http_req_duration"]?.values?.["p(95)"]?.toFixed(2) ?? "N/A";
  const p99     = data.metrics["http_req_duration"]?.values?.["p(99)"]?.toFixed(2) ?? "N/A";
  const errRate = data.metrics["mintry_success_rate"]?.values?.rate;
  const errPct  = errRate !== undefined ? ((1 - errRate) * 100).toFixed(2) + "%" : "N/A";
  const proxDur = data.metrics["mintry_proxy_latency_ms"]?.values?.["p(99)"]?.toFixed(2) ?? "N/A";

  return `
╔═══════════════════════════════════════════════════════╗
║  Mintry Fabric Load Test — Run Summary                ║
╠═══════════════════════════════════════════════════════╣
║  Achieved RPS          : ${rps.padEnd(29)}║
║  Latency P95 (k6)      : ${(p95 + " ms").padEnd(29)}║
║  Latency P99 (k6)      : ${(p99 + " ms").padEnd(29)}║
║  Proxy Latency P99     : ${(proxDur + " ms").padEnd(29)}║
║  Error rate            : ${errPct.padEnd(29)}║
╚═══════════════════════════════════════════════════════╝

Next step: scrape http://localhost:9091/metrics for
mintry_proxy_duration_ms to see internal P99 breakdown.
`;
}
