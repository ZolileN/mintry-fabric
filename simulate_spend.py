#!/usr/bin/env python3
"""
Mintry Fabric — Interactive Investor Demo
══════════════════════════════════════════════════════════════════
Dynamically fetches active agents from the control plane and 
simulates real-world traffic to demonstrate live budget enforcement.
"""
import sys
import time
import httpx
import sqlite3
import argparse
import mintry
from mintry import MintryMandateExceeded
from mintry.interceptors.global_http import _flush_metering_queue

# ── ANSI colors ──────────────────────────────────────────────────────────────
G   = "\033[92m"   # green
Y   = "\033[93m"   # yellow
R   = "\033[91m"   # red
B   = "\033[94m"   # blue
W   = "\033[97m"   # bright white
DIM = "\033[2m"
BLD = "\033[1m"
RST = "\033[0m"

parser = argparse.ArgumentParser(description="Simulate agent spend for Mintry Fabric demo")
parser.add_argument("--agent", type=str, help="The mandate ID to spend on")
parser.add_argument("--tasks", type=int, default=5, help="Number of tasks to simulate")
args = parser.parse_args()

print(f"\n{BLD}  🚀  Mintry Fabric — Investor Demo Engine{RST}")
print(f"{DIM}══════════════════════════════════════════════════════════{RST}")

engine = mintry.init(
    api_key="demo_key",
    db_path="test_data/local.db",
)

# Fetch active agents
conn = sqlite3.connect("test_data/local.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT id, max_usd, spent_usd FROM mandates WHERE status = 'active' ORDER BY id ASC")
active_agents = cursor.fetchall()
conn.close()

if not active_agents:
    print(f"  {R}❌  No active agents found in the database. Please create one in the dashboard.{RST}\n")
    sys.exit(1)

agent_id = args.agent

if not agent_id:
    print(f"\n  {B}📋  Available Active Agents:{RST}")
    for idx, row in enumerate(active_agents):
        print(f"       [{idx + 1}] {W}{row['id']}{RST}  (Budget: ${row['max_usd']:.2f}, Spent: ${row['spent_usd']:.4f})")
    print()
    try:
        choice = input(f"  {Y}👉  Select an agent number to simulate spend (or type name): {RST}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(active_agents):
            agent_id = active_agents[int(choice) - 1]["id"]
        else:
            agent_id = choice
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

# Verify agent exists and is active
agent_record = next((a for a in active_agents if a["id"] == agent_id), None)
if not agent_record:
    try:
        state = engine.wallet.get_mandate(agent_id)
        if state["status"] != "active":
            print(f"\n  {R}🛑  Agent '{agent_id}' is currently {state['status'].upper()}. Cannot spend.{RST}\n")
            sys.exit(1)
    except Exception:
        print(f"\n  {R}❌  Agent '{agent_id}' not found.{RST}\n")
        sys.exit(1)

print(f"\n  {B}🎯  Target locked:{RST} {W}{agent_id}{RST}")
state = engine.wallet.get_mandate(agent_id)
print(f"  {G}💸  Current Budget:{RST} ${state['budget_usd']:.2f}  │  {Y}Already Spent:{RST} ${state['spent_usd']:.4f}\n")

# Fake transport for OpenAI to simulate expensive agent tasks
def _fake_openai(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-demo",
            "object": "chat.completion",
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 12000,
                "completion_tokens": 25000,
                "total_tokens": 37000,
            },
            "choices": [{
                "message": {"role": "assistant", "content": "Task completed successfully."},
                "finish_reason": "stop",
            }],
        },
        request=request,
    )

print(f"  {DIM}Simulating high-throughput traffic via OpenAI API...{RST}\n")

try:
    for i in range(1, args.tasks + 1):
        with httpx.Client(transport=httpx.MockTransport(_fake_openai)) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Execute agent pipeline."}]},
                headers={"x-mintry-mandate": agent_id, "Authorization": "Bearer fake"}
            )
            
        # Flush the background queue so the DB updates instantly for the demo
        _flush_metering_queue()
        
        state = engine.wallet.get_mandate(agent_id)
        
        # Calculate headroom properly
        headroom = state['budget_usd'] - state['spent_usd']
        if headroom < 0: headroom = 0
            
        print(f"  {G}✔  Task {i} complete{RST}  │  Total Spent: {W}${state['spent_usd']:.4f}{RST}  │  Remaining: {Y}${headroom:.4f}{RST}")
        time.sleep(0.8)

except MintryMandateExceeded as exc:
    print()
    print(f"{DIM}══════════════════════════════════════════════════════════{RST}")
    print(f"  {R}{BLD}🛑  KILL-SWITCH FIRED!{RST}")
    print(f"  {W}The Mintry Logic Fabric intercepted the request for {agent_id}.{RST}")
    print(f"  {DIM}Reason:{RST} {exc}")
    print(f"{DIM}══════════════════════════════════════════════════════════{RST}")

print(f"\n  {G}✅  Demo run complete!{RST} Check the observability dashboard to see the live telemetry.\n")
