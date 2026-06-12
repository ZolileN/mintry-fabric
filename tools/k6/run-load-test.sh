#!/usr/bin/env bash
# =============================================================================
# tools/k6/run-load-test.sh
#
# Mintry Fabric — Load Test Runner
#
# Orchestrates the full load testing sequence:
#   1. Preflight checks (mock server + Mintry up)
#   2. Kernel tuning (dry-run by default unless --tune flag passed)
#   3. Scrape a Prometheus snapshot before the run
#   4. Run the selected k6 script
#   5. Scrape Prometheus snapshot after the run
#   6. Print the proxy overhead delta
#
# USAGE
# -----
#   bash tools/k6/run-load-test.sh                    # smoke test (50 RPS)
#   bash tools/k6/run-load-test.sh --full             # full ceiling hunt (10k RPS)
#   bash tools/k6/run-load-test.sh --compare          # direct vs proxy comparison
#   bash tools/k6/run-load-test.sh --mandate-stress   # mandate enforcement stress
#   bash tools/k6/run-load-test.sh --tune --full      # apply kernel tuning + full run
# =============================================================================

set -euo pipefail

# ─── Colour helpers ───────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
RED='\033[0;31m';   BOLD='\033[1m';       NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()     { echo -e "${RED}[FAIL]${NC}  $*" >&2; }
section() { echo -e "\n${BOLD}$*${NC}"; echo "────────────────────────────────────────"; }

# ─── Defaults ─────────────────────────────────────────────────────────────────
SCRIPT="tools/k6/mintry-baseline.js"
K6_EXTRA_ARGS=""
TUNE_KERNEL=false
FULL_RUN=false

# ─── Ensure Go-installed binaries are on PATH ─────────────────────────────────
# go install go.k6.io/k6@latest places the binary in $(go env GOPATH)/bin,
# which is not automatically on PATH in non-interactive shells.
if command -v go &> /dev/null; then
  GOPATH_BIN="$(go env GOPATH)/bin"
  if [[ -x "${GOPATH_BIN}/k6" ]]; then
    export PATH="${GOPATH_BIN}:${PATH}"
    info "Found k6 at ${GOPATH_BIN}/k6 — added to PATH"
  fi
fi

# ─── Argument parsing ─────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --tune)           TUNE_KERNEL=true ;;
    --full)           FULL_RUN=true; K6_EXTRA_ARGS="--env TARGET_RPS=10000" ;;
    --smoke)          K6_EXTRA_ARGS="--env SMOKE=true" ;;
    --compare)        SCRIPT="tools/k6/mintry-direct-vs-proxy.js" ;;
    --mandate-stress) SCRIPT="tools/k6/mintry-mandate-stress.js" ;;
    *) warn "Unknown flag: $arg" ;;
  esac
done

mkdir -p tools/k6/results

section "1/5 — Preflight checks"

# Gemini mock server
if curl -sf http://localhost:9090/health > /dev/null 2>&1; then
  ok "Gemini mock server reachable at localhost:9090"
else
  err "Gemini mock server not running on localhost:9090"
  err "Start it: ./tools/gemini-mock-server/gemini-mock"
  exit 1
fi

# Mintry proxy (optional for direct-mode scripts)
# Check common ports: 8000 (default), 9001 (alt)
MINTRY_PORT=""
for port in 8000 9001 8080 3000; do
  if curl -sf "http://localhost:${port}/api/summary" > /dev/null 2>&1; then
    MINTRY_PORT="$port"
    ok "Mintry proxy reachable at localhost:${port}"
    break
  fi
done
if [[ -z "$MINTRY_PORT" ]]; then
  warn "Mintry not responding on ports 8000/9001/8080/3000 — fiscal enforcement inactive"
  warn "Start it: MINTRY_OTEL_ENABLED=1 uv run mintry dashboard --db test_data/local.db"
fi

# Prometheus metrics
if curl -sf http://localhost:9091/metrics > /dev/null 2>&1; then
  ok "Prometheus metrics endpoint at localhost:9091"
else
  warn "OTel metrics not active — start Mintry with MINTRY_OTEL_ENABLED=1"
fi

# k6
if ! command -v k6 &> /dev/null; then
  err "k6 not found. Install with: go install go.k6.io/k6@latest"
  err "Or via apt: sudo gpg ... (see https://k6.io/docs/get-started/installation/)"
  exit 1
fi
ok "k6 $(k6 version | head -1)"

# ─── Step 2: Kernel tuning ────────────────────────────────────────────────────
section "2/5 — Kernel tuning"

if [[ "$TUNE_KERNEL" == "true" ]]; then
  if [[ "$EUID" -ne 0 ]]; then
    warn "Not running as root — using sudo for kernel tuning"
    sudo bash scripts/tune-kernel.sh
  else
    bash scripts/tune-kernel.sh
  fi
else
  info "Kernel tuning skipped (pass --tune to apply)"
  info "Recommended before full 10k RPS run: bash scripts/tune-kernel.sh --dry-run"
fi

# ─── Step 3: Pre-run Prometheus snapshot ─────────────────────────────────────
section "3/5 — Pre-run metrics snapshot"

PRE_SNAPSHOT="tools/k6/results/pre-run-$(date +%Y%m%dT%H%M%S).txt"
if curl -sf http://localhost:9091/metrics | grep -E "^mintry_" > "$PRE_SNAPSHOT" 2>/dev/null; then
  ok "Prometheus snapshot saved: $PRE_SNAPSHOT"
  grep "mintry_proxy_duration_ms_count" "$PRE_SNAPSHOT" || true
else
  warn "Could not snapshot Prometheus metrics (OTel may be disabled)"
fi

# ─── Step 4: Run k6 ──────────────────────────────────────────────────────────
section "4/5 — k6 load test"

info "Script : $SCRIPT"
info "Args   : $K6_EXTRA_ARGS"
info "Results: tools/k6/results/"
echo ""

# shellcheck disable=SC2086
k6 run $K6_EXTRA_ARGS "$SCRIPT"
K6_EXIT=$?

# ─── Step 5: Post-run Prometheus snapshot + delta ────────────────────────────
section "5/5 — Post-run metrics"

POST_SNAPSHOT="tools/k6/results/post-run-$(date +%Y%m%dT%H%M%S).txt"
if curl -sf http://localhost:9091/metrics | grep -E "^mintry_" > "$POST_SNAPSHOT" 2>/dev/null; then
  ok "Post-run snapshot: $POST_SNAPSHOT"
  echo ""
  echo "  mintry_proxy_duration_ms histogram (internal proxy latency):"
  grep "mintry_proxy_duration_ms" "$POST_SNAPSHOT" | grep -v "^#" | head -20
else
  warn "Could not capture post-run Prometheus metrics"
fi

echo ""
if [[ $K6_EXIT -eq 0 ]]; then
  ok "Load test completed — all thresholds passed ✅"
else
  warn "Load test completed with threshold violations (exit code $K6_EXIT)"
fi
