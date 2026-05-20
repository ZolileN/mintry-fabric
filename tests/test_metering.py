import pytest
import mintry
from mintry.interceptors.global_http import GlobalHTTPInterceptor
from openai import OpenAI
from decimal import Decimal


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and use a fresh temp database for every test."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


def test_real_time_metering(httpx_mock, tmp_path):
    # Initialize Fabric with an isolated temp database
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")
    mandate_id = "mt_task_882x"

    # 1. Capture initial spend
    initial_spent = fabric.wallet.get_spent(mandate_id)

    # 2. Mock a 2000-token response from OpenAI
    # Based on our $5/1M pricing, this should cost exactly $0.01
    mock_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-5-preview",
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 1000,
            "total_tokens": 2000
        },
        "choices": [{"message": {"role": "assistant", "content": "I am a metered agent."}}]
    }

    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json=mock_response,
        status_code=200
    )

    print(f"\n--- Phase 1: Executing Metered Request ---")
    client.chat.completions.create(
        model="gpt-5-preview",
        messages=[{"role": "user", "content": "Generate 1000 tokens of text."}]
    )

    # 3. Verify the Ledger
    final_spent = fabric.wallet.get_spent(mandate_id)
    delta = final_spent - initial_spent

    print(f"[TEST] Initial Spent: ${initial_spent:.6f}")
    print(f"[TEST] Final Spent: ${final_spent:.6f}")
    print(f"[TEST] Calculated Delta: ${delta:.6f}")

    # Expected: 2000 * 0.000005 = 0.01
    assert delta == pytest.approx(0.01, rel=1e-5)
    print("\n[SUCCESS] Logic Fabric Metered the exact token cost.")
