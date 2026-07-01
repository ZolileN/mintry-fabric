#!/usr/bin/env python3
"""
Kill-Switch Demo — The "Aha!" Moment
══════════════════════════════════════════════════════════════════
Watch the Mintry Logic Fabric enforce a hard budget cap live.

  • Two requests go through — tokens flow, spend accumulates.
  • The third request hits the cap. The fabric kills it.
  • MintryMandateExceeded propagates up and terminates the script.

Run:
    uv run python kill_switch_demo.py
══════════════════════════════════════════════════════════════════
"""
import sys
import time
import httpx
import mintry
from mintry import MintryMandateExceeded
from mintry.interceptors.global_http import _flush_metering_queue

# ── ANSI colours ──────────────────────────────────────────────────────────────
G   = "\033[92m"   # green
Y   = "\033[93m"   # yellow
R   = "\033[91m"   # red
B   = "\033[94m"   # blue
W   = "\033[97m"   # bright white
DIM = "\033[2m"
BLD = "\033[1m"
RST = "\033[0m"

def hr(char="─", n=62):
    print(f"{DIM}{char * n}{RST}")

def log_ok(msg):    print(f"  {G}✔{RST}  {msg}")
def log_live(msg):  print(f"  {Y}⚡{RST}  {msg}")
def log_info(msg):  print(f"  {B}ℹ{RST}  {msg}")

# ── Banner ────────────────────────────────────────────────────────────────────
print()
print(f"{BLD}  🔐  Mintry Logic Fabric — Kill-Switch Demo{RST}")
hr("═")

# ── Init ──────────────────────────────────────────────────────────────────────
engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)
hr()

# Use a timestamped mandate so the demo is always fresh
MANDATE_ID = f"kill_switch_{int(time.time())}"

# Budget math (gpt-4o pricing):
#   500 prompt  × $0.0000025 = $0.00125
#   500 output  × $0.00001   = $0.00500
#   per-call cost             = $0.00625
#
#   Budget $0.02 → 2 calls succeed ($0.0125 spent, $0.0075 remaining)
#                  3rd call: remaining $0.0075 < $0.01 threshold → BLOCKED
BUDGET = 0.02

engine.wallet.create_mandate(MANDATE_ID, BUDGET)
state = engine.wallet.get_mandate(MANDATE_ID)

print(f"\n  {W}Mandate ID :{RST}  {BLD}{MANDATE_ID}{RST}")
print(f"  {W}Hard Cap   :{RST}  {BLD}${state['budget_usd']:.2f}{RST}")
print(f"  {W}Model      :{RST}  gpt-4o  (500 prompt + 500 completion tokens/req)")
print(f"  {W}Cost/req   :{RST}  ~$0.0063")
print(f"  {W}Threshold  :{RST}  fabric blocks when remaining < $0.01")
hr()
print()

# ── Fake transport — no real network calls ────────────────────────────────────
def _fake_openai(request: httpx.Request) -> httpx.Response:
    """Returns a realistic OpenAI response so the metering pipeline fires."""
    return httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-killswitch-demo",
            "object": "chat.completion",
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 500,
                "total_tokens": 1000,
            },
            "choices": [{
                "message": {"role": "assistant", "content": "Summarisation complete."},
                "finish_reason": "stop",
            }],
        },
        request=request,
    )

# ── Main loop — runs until the kill-switch fires ──────────────────────────────
print(f"  Firing requests at {BLD}api.openai.com{RST}…\n")

try:
    for i in range(1, 10):
        state     = engine.wallet.get_mandate(MANDATE_ID)
        spent     = state["spent_usd"]
        remaining = state["budget_usd"] - spent

        log_live(
            f"Request #{i}  │  "
            f"spent {Y}${spent:.4f}{RST}  │  "
            f"remaining {W}${remaining:.4f}{RST}"
        )

        # ── This call goes through the interceptor pre-flight check ─────────
        # If remaining < $0.01 the fabric raises MintryMandateExceeded HERE,
        # before touching the network.
        with httpx.Client(transport=httpx.MockTransport(_fake_openai)) as client:
            client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": f"Summarise document batch {i}."}],
                },
                headers={"X-Mintry-Mandate": MANDATE_ID},
            )

        # Flush the async metering queue so wallet cache is updated before
        # the next iteration's pre-flight check reads it
        _flush_metering_queue()

        state = engine.wallet.get_mandate(MANDATE_ID)
        log_ok(
            f"Accepted  │  "
            f"new spend {G}${state['spent_usd']:.4f}{RST}  │  "
            f"headroom {W}${state['budget_usd'] - state['spent_usd']:.4f}{RST}"
        )
        print()

except MintryMandateExceeded as exc:
    final = engine.wallet.get_mandate(MANDATE_ID)
    print()
    hr("═")
    print(f"\n  {R}{BLD}🛑  KILL-SWITCH FIRED{RST}\n")
    print(f"  {W}Mandate  :{RST}  {exc.task}")
    print(f"  {W}Hard Cap :{RST}  {R}${exc.cap:.4f}{RST}")
    print(f"  {W}Spent    :{RST}  {R}${exc.spent:.4f}{RST}")
    print(f"  {W}Headroom :{RST}  {R}${exc.cap - exc.spent:.4f}{RST}  (below $0.01 threshold)")
    print()
    print(f"  {DIM}The fabric intercepted the request at the transport layer.{RST}")
    print(f"  {DIM}No tokens were sent. No money was spent on this call.{RST}")
    print()
    hr("═")
    print()
    sys.exit(1)
