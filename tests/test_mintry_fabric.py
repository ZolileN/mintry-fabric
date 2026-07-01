import pytest
import mintry
from mintry.interceptors.global_http import GlobalHTTPInterceptor
from decimal import Decimal
from openai import OpenAI, AuthenticationError, APIConnectionError


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and use a fresh temp database for every test."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_logic_fabric_enforcement(tmp_path, httpx_mock):
    """shield() creates a real mandate that is enforced when budget is exhausted."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")

    # Mock response that costs $0.005 per call (1000 tokens * $0.000005)
    mock_response = {
        "id": "chatcmpl-enforce",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-5-preview",
        "usage": {"prompt_tokens": 500, "completion_tokens": 500, "total_tokens": 1000},
        "choices": [{"message": {"role": "assistant", "content": "metered."}}]
    }

    with fabric.shield(task="budget_test", max_usd=0.02) as mandate:
        # Verify shield() created a real mandate with a dynamic ID
        assert mandate.id.startswith("mt_")
        assert mandate.task == "budget_test"
        assert mandate.max_usd == 0.02

        # Verify the mandate exists in the database
        data = fabric.wallet.get_mandate(mandate.id)
        assert data["budget_usd"] == 0.02
        assert data["spent_usd"] == 0.0

        blocked = False
        for i in range(20):
            # Check budget BEFORE registering a mock — if budget is exhausted,
            # the next request will be blocked pre-flight and the mock won't be consumed
            remaining = fabric.wallet.get_mandate(mandate.id)
            headroom = remaining["budget_usd"] - remaining["spent_usd"]

            if headroom >= 0.01:
                httpx_mock.add_response(
                    method="POST",
                    url="https://api.openai.com/v1/chat/completions",
                    json=mock_response,
                    status_code=200
                )

            try:
                print(f"Attempting Request #{i+1}...")
                client.chat.completions.create(
                    model="gpt-5-preview",
                    messages=[{"role": "user", "content": "loop"}],
                    extra_headers={"X-Mintry-Mandate": mandate.id}
                )
            except (PermissionError, APIConnectionError) as e:
                error_msg = str(e)
                cause_msg = str(e.__cause__) if e.__cause__ else ""
                if "Mintry" in error_msg or "Mintry" in cause_msg:
                    print(f"\n[SUCCESS] Fabric Intervened at Request #{i+1}")
                    print(f"Reason: {e}")
                    # Verify the error includes budget details (Task 11)
                    assert "Hard Cap:" in error_msg or "Hard Cap:" in cause_msg
                    blocked = True
                    break
                raise e

        assert blocked, "Fabric should have blocked the request loop but didn't."