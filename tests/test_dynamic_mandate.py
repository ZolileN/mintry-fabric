import pytest
import mintry
from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import Mandate
from decimal import Decimal
from openai import OpenAI, APIConnectionError


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and use a fresh temp database for every test."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


def test_shield_creates_real_mandate(tmp_path):
    """shield() must create a mandate in the database and exhaust it on exit."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    with fabric.shield(task="research-analysis", max_usd=2.50) as mandate:
        # 1. Verify the returned Mandate object
        assert isinstance(mandate, Mandate)
        assert mandate.id.startswith("mt_")
        assert len(mandate.id) == 15  # "mt_" + 12 hex chars
        assert mandate.task == "research-analysis"
        assert mandate.max_usd == 2.50

        # 2. Verify it exists in the database with correct budget
        data = fabric.wallet.get_mandate(mandate.id)
        assert data["budget_usd"] == 2.50
        assert data["spent_usd"] == 0.0

        saved_id = mandate.id

    # 3. After exiting the context, mandate should be exhausted
    row = fabric.wallet.conn.execute(
        "SELECT status FROM mandates WHERE id = ?", (saved_id,)
    ).fetchone()
    assert row[0] == "exhausted"
    print(f"\n[SUCCESS] shield() lifecycle: created → yielded → exhausted ({saved_id})")


def test_dynamic_mandate_routing(tmp_path, httpx_mock):
    """Requests with X-Mintry-Mandate header are billed to the correct mandate."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")

    # Create two mandates with different budgets
    fabric.wallet.create_mandate("task_alpha", 1.00)
    fabric.wallet.create_mandate("task_beta", 0.50)

    mock_response = {
        "id": "chatcmpl-route",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-5-preview",
        "usage": {"prompt_tokens": 500, "completion_tokens": 500, "total_tokens": 1000},
        "choices": [{"message": {"role": "assistant", "content": "Routed response."}}]
    }

    # Send request routed to task_alpha
    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json=mock_response,
        status_code=200
    )

    client.chat.completions.create(
        model="gpt-5-preview",
        messages=[{"role": "user", "content": "Hello"}],
        extra_headers={"X-Mintry-Mandate": "task_alpha"}
    )

    # Verify spend was attributed to task_alpha, not task_beta
    alpha_spent = fabric.wallet.get_spent("task_alpha")
    beta_spent = fabric.wallet.get_spent("task_beta")

    # 1000 tokens * $0.000005 = $0.005
    assert alpha_spent == pytest.approx(0.005, rel=1e-5)
    assert beta_spent == 0.0

    print(f"\n[SUCCESS] Dynamic routing: task_alpha=${alpha_spent:.6f}, task_beta=${beta_spent:.6f}")


def test_budget_exhausted_error_includes_details(tmp_path):
    """PermissionError messages must include mandate_id, budget, spent, and remaining."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")

    # Create a mandate with very low budget and drain it
    fabric.wallet.create_mandate("broke_mandate", 0.005)
    fabric.wallet.record_usage("broke_mandate", 0.005)

    try:
        client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": "test"}],
            extra_headers={"X-Mintry-Mandate": "broke_mandate"}
        )
        pytest.fail("Should have raised PermissionError")
    except (PermissionError, APIConnectionError) as e:
        error_msg = str(e)
        cause_msg = str(e.__cause__) if e.__cause__ else ""
        full_msg = error_msg + cause_msg

        # Verify actionable details are present
        assert "broke_mandate" in full_msg
        assert "Budget:" in full_msg
        assert "Spent:" in full_msg
        assert "Remaining:" in full_msg
        print(f"\n[SUCCESS] Error message includes details: {e}")


def test_init_rejects_empty_api_key(tmp_path):
    """mintry.init() must reject empty or missing API keys."""
    db = str(tmp_path / "vouchers.db")

    with pytest.raises(ValueError, match="MINTRY_API_KEY"):
        mintry.init(api_key="", db_path=db)

    with pytest.raises(ValueError, match="MINTRY_API_KEY"):
        mintry.init(api_key=None, db_path=db)

    print("\n[SUCCESS] Empty API keys are rejected with ValueError.")
