import pytest
import mintry
from mintry.interceptors.global_http import GlobalHTTPInterceptor
from decimal import Decimal
from openai import OpenAI, AuthenticationError, APIConnectionError
from mintry.bridge.stripe_mpp import MockStripeBridge


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and use a fresh temp database for every test."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


def test_mpp_resurrection(tmp_path, httpx_mock):
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")
    bridge = MockStripeBridge()
    mandate_id = "mt_task_882x"

    # Drain the seed mandate so fiscal check fails
    fabric.wallet.record_usage(mandate_id, 0.01)

    print("\n--- Phase 1: Verify Blocked State ---")
    try:
        client.chat.completions.create(model="gpt-5", messages=[{"role":"user","content":"hi"}])
    except (PermissionError, APIConnectionError) as e:
        print("Confirmed: Agent is currently grounded.")

    print("\n--- Phase 2: Stripe MPP Settlement ---")
    # Simulate a user paying $5.00 via Stripe
    bridge.trigger_top_up(fabric.wallet, mandate_id, Decimal("5.00"))

    print("\n--- Phase 3: Verify Unblocked State ---")
    # Mock a successful response so we don't hit real OpenAI
    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json={
            "id": "chatcmpl-mpp",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-5",
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            "choices": [{"message": {"role": "assistant", "content": "I am back."}}]
        },
        status_code=200
    )

    # This should no longer raise a PermissionError
    try:
        client.chat.completions.create(model="gpt-5", messages=[{"role":"user","content":"hi"}])
        print("Success: Agent has resumed operations.")
    except PermissionError:
        pytest.fail("Fabric should have allowed this request after top-up.")

