import httpx
import mintry
from mintry.interceptors.global_http import _flush_metering_queue

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

engine.wallet.create_mandate("smoke_task", 100.00)
print(engine.wallet.get_mandate("smoke_task"))
# {'budget_usd': 100.0, 'spent_usd': 0.0, 'status': 'active', 'expires_at': None}

# Make a metered request through the interceptor.
# The patched httpx.Client.send fires, sees api.openai.com, runs pre/post-flight metering.
def _fake_openai(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-smoke",
            "object": "chat.completion",
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 500, "completion_tokens": 500, "total_tokens": 1000},
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
        },
        request=request,
    )

with httpx.Client(transport=httpx.MockTransport(_fake_openai)) as client:
    client.post(
        "https://api.openai.com/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Mintry-Mandate": "smoke_task"},
    )

# Wait for the async metering worker to flush the spend to the wallet
_flush_metering_queue()

# Re-fetch to see updated spend
mandate = engine.wallet.get_mandate("smoke_task")
print(f"Spent: ${mandate['spent_usd']:.4f} / ${mandate['budget_usd']:.2f}")
# gpt-4o: 500 * $0.0000025 + 500 * $0.00001 = $0.00125 + $0.005 = $0.00625
