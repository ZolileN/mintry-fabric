#!/usr/bin/env python3
"""
Marketing Agent Demo
══════════════════════════════════════════════════════════════════
Simulates a marketing agent generating copy and spending budget.
"""
import sys
import time
import httpx
import mintry
from mintry import MintryMandateExceeded
from mintry.interceptors.global_http import _flush_metering_queue

print("\n  🚀  Initializing Marketing Agent...")

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

MANDATE_ID = "marketing_agent"
BUDGET = 25.00

# Create or reset the mandate
try:
    engine.wallet.create_mandate(MANDATE_ID, BUDGET)
except Exception:
    pass

# Fake transport for OpenAI to simulate expensive marketing tasks
def _fake_openai(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-marketing",
            "object": "chat.completion",
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 12000,
                "completion_tokens": 45000,
                "total_tokens": 57000,
            },
            "choices": [{
                "message": {"role": "assistant", "content": "Generated 5 SEO blog posts and social media copy."},
                "finish_reason": "stop",
            }],
        },
        request=request,
    )

print(f"  💸  Allocated Budget: ${BUDGET:.2f}\n")

try:
    # Run a batch of 5 expensive tasks
    for i in range(1, 6):
        with httpx.Client(transport=httpx.MockTransport(_fake_openai)) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Write a 5000 word SEO blog..."}]},
                headers={"x-mintry-mandate": MANDATE_ID, "Authorization": "Bearer fake"}
            )
            
        # Flush the background queue so the DB updates instantly for the demo
        _flush_metering_queue()
        
        state = engine.wallet.get_mandate(MANDATE_ID)
        print(f"  ✔  Task {i} complete  │  Total Spent: ${state['spent_usd']:.4f}  │  Remaining: ${state['budget_usd'] - state['spent_usd']:.4f}")
        time.sleep(0.5)

except MintryMandateExceeded as exc:
    print(f"\n  🛑  AGENT BLOCKED: {exc}")

print("\n  ✅  Marketing batch completed! Check the dashboard to see the live metrics.")
print()
