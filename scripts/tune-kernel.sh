#!/usr/bin/env bash
# =============================================================================
# Mintry Fabric — Linux Kernel Network Tuning Script
# scripts/tune-kernel.sh
#
# PURPOSE
# -------
# Applies OS-level socket settings that prevent the Linux networking stack
# from becoming a bottleneck during high-throughput load testing (target:
# 10,000 RPS through the Mintry proxy).
#
# Without these settings, the kernel will impose default limits on:
#   - Open file descriptors  → concurrent connection count ceiling
#   - Ephemeral port range   → port exhaustion at high connection churn
#   - TIME_WAIT recycling    → stale sockets consuming ports between tests
#
# USAGE
# -----
#   sudo bash scripts/tune-kernel.sh          # apply settings
#   sudo bash scripts/tune-kernel.sh --dry-run  # print what would be run
#
# PERSISTENCE
# -----------
# ulimit settings apply only to the current shell session and its children.
# To make sysctl changes persistent across reboots, add the relevant lines
# to /etc/sysctl.d/99-mintry-perf.conf and run `sysctl --system`.
#
# REVERTING
# ---------
# sysctl changes are reset automatically on reboot.  To revert immediately:
#   sysctl -w net.ipv4.ip_local_port_range="32768 60999"
#   sysctl -w net.ipv4.tcp_tw_reuse=0
# =============================================================================

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# Colour helpers ──────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

run() {
    local cmd="$*"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}[DRY ]${NC}  $cmd"
    else
        eval "$cmd"
        ok "$cmd"
    fi
}

# ─── Root check ───────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "false" ]] && [[ "$EUID" -ne 0 ]]; then
    err "This script must be run as root (or with sudo) to modify sysctl values."
    err "Try: sudo bash scripts/tune-kernel.sh"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "   Mintry Fabric — Linux Kernel Network Tuning"
if [[ "$DRY_RUN" == "true" ]]; then
    echo "   MODE: DRY RUN (no changes will be applied)"
fi
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# ─── 1. File descriptor limit ────────────────────────────────────────────────
info "Setting maximum open file descriptors to 65535"
info "  Rationale: each concurrent socket consumes one file descriptor."
info "  The default (1024) is hit almost immediately at 10k RPS."
run "ulimit -n 65535"
echo ""

# ─── 2. Ephemeral port range ─────────────────────────────────────────────────
info "Expanding ephemeral port range to 1024-65535"
info "  Rationale: high-churn HTTP/1.1 short-lived connections exhaust the"
info "  default range (32768-60999 = ~28k ports) quickly at 10k RPS."
info "  Expanding to ~64k ports prevents EADDRINUSE errors."
run "sysctl -w net.ipv4.ip_local_port_range='1024 65535'"
echo ""

# ─── 3. TIME_WAIT socket reuse ───────────────────────────────────────────────
info "Enabling aggressive TIME_WAIT socket reuse (tcp_tw_reuse=1)"
info "  Rationale: after a connection closes, Linux holds the socket in"
info "  TIME_WAIT for 2×MSL (~60s) by default.  At 10k RPS this creates a"
info "  backlog of ~600k lingering sockets.  tcp_tw_reuse allows the kernel"
info "  to safely reuse these ports for outbound connections immediately."
run "sysctl -w net.ipv4.tcp_tw_reuse=1"
echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════"
if [[ "$DRY_RUN" == "true" ]]; then
    warn "DRY RUN complete — no kernel parameters were modified."
    warn "Remove --dry-run and re-run as root to apply."
else
    ok "Kernel tuning applied successfully."
    echo ""
    echo "  To verify:"
    echo "    ulimit -n                           # should show 65535"
    echo "    sysctl net.ipv4.ip_local_port_range # should show 1024 65535"
    echo "    sysctl net.ipv4.tcp_tw_reuse        # should show 1"
    echo ""
    echo "  To persist across reboots:"
    echo "    echo 'net.ipv4.ip_local_port_range=1024 65535' | sudo tee -a /etc/sysctl.d/99-mintry-perf.conf"
    echo "    echo 'net.ipv4.tcp_tw_reuse=1'                 | sudo tee -a /etc/sysctl.d/99-mintry-perf.conf"
    echo "    sudo sysctl --system"
fi
echo "═══════════════════════════════════════════════════════════════════"
