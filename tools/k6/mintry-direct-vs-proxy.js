/**
 * tools/k6/mintry-direct-vs-proxy.js
 *
 * Mintry Fabric — k6 Comparative Benchmark
 * =========================================
 *
 * Runs TWO scenarios back-to-back in the same k6 invocation:
 *
 *   1. "direct"  — k6 → Gemini mock server directly (no Mintry)
 *   2. "proxy"   — k6 → Mintry → Gemini mock server
 *
 * The difference in P99 latency between the two scenarios is your
 * definitive Mintry proxy overhead measurement.
 *
 * HOW TO RUN
 * ----------
 *   k6 run tools/k6/mintry-direct-vs-proxy.js
 *
 * READING THE RESULTS
 * -------------------
 * Look at the `scenario` tag in the output:
 *
 *   http_req_duration{scenario:direct} p(99) = Xms   ← mock server + loopback
 *   http_req_duration{scenario:proxy}  p(99) = Yms   ← Mintry + mock + loopback
 *
 *   Proxy overhead P99 = Y - X  (target: < 1ms)
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const directLatency = new Trend("direct_latency_ms", true);
const proxyLatency  = new Trend("proxy_latency_ms", true);

const PAYLOAD = JSON.stringify({
  contents: [{ role: "user", parts: [{ text: "benchmark probe" }] }],
});

const HEADERS = { "Content-Type": "application/json" };

export const options = {
  scenarios: {
    direct: {
      executor: "ramping-arrival-rate",
      startRate: 0,
      timeUnit: "1s",
      preAllocatedVUs: 100,
      maxVUs: 500,
      stages: [
        { duration: "15s", target: 200 },
        { duration: "30s", target: 200 },
        { duration: "15s", target: 0   },
      ],
      env: { SCENARIO: "direct" },
      gracefulStop: "5s",
    },
    proxy: {
      executor: "ramping-arrival-rate",
      startRate: 0,
      timeUnit: "1s",
      preAllocatedVUs: 100,
      maxVUs: 500,
      startTime: "65s",  // run after the direct scenario completes
      stages: [
        { duration: "15s", target: 200 },
        { duration: "30s", target: 200 },
        { duration: "15s", target: 0   },
      ],
      env: { SCENARIO: "proxy" },
      gracefulStop: "5s",
    },
  },

  thresholds: {
    "direct_latency_ms": [{ threshold: "p(99)<50" }],
    "proxy_latency_ms":  [{ threshold: "p(99)<100" }],
  },

  summaryTrendStats: ["avg", "med", "p(95)", "p(99)", "p(99.9)", "max"],
};

const ENDPOINT = "/v1beta/models/gemini-2.0-flash:generateContent";

export default function () {
  const isDirect = __ENV.SCENARIO === "direct";
  const base     = isDirect ? "http://localhost:9090" : "http://localhost:8000";

  const t0  = Date.now();
  const res = http.post(`${base}${ENDPOINT}`, PAYLOAD, {
    headers: HEADERS,
    timeout: "5s",
    tags: { target: isDirect ? "mock" : "mintry" },
  });
  const elapsed = Date.now() - t0;

  if (isDirect) directLatency.add(elapsed);
  else          proxyLatency.add(elapsed);

  check(res, { "status 200": (r) => r.status === 200 });
}

export function handleSummary(data) {
  const d99 = data.metrics["direct_latency_ms"]?.values?.["p(99)"]?.toFixed(2) ?? "N/A";
  const p99 = data.metrics["proxy_latency_ms"]?.values?.["p(99)"]?.toFixed(2)  ?? "N/A";
  const overhead = (d99 !== "N/A" && p99 !== "N/A")
    ? (parseFloat(p99) - parseFloat(d99)).toFixed(2) + " ms"
    : "N/A";

  return {
    "tools/k6/results/comparison-run.json": JSON.stringify(data, null, 2),
    stdout: `
╔═══════════════════════════════════════════════════════╗
║  Mintry Direct vs Proxy — P99 Comparison             ║
╠═══════════════════════════════════════════════════════╣
║  Direct (mock only)  P99: ${(d99 + " ms").padEnd(29)}║
║  Proxy (Mintry+mock) P99: ${(p99 + " ms").padEnd(29)}║
║  ─────────────────────────────────────────────────── ║
║  Mintry overhead     P99: ${overhead.padEnd(29)}║
╚═══════════════════════════════════════════════════════╝
`,
  };
}
