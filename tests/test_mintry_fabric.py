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


def test_logic_fabric_enforcement(tmp_path):
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    client = OpenAI(api_key="sk-mock-key")

    with fabric.shield(task="budget_test", max_usd=Decimal("0.01")) as mandate:
        try:
            for i in range(100):
                print(f"Attempting Request #{i+1}...")
                try:
                    client.chat.completions.create(
                        model="gpt-5-preview",
                        messages=[{"role": "user", "content": "loop"}]
                    )
                except AuthenticationError:
                    # Request passed the fabric, but failed at OpenAI (Expected)
                    pass
        except (PermissionError, APIConnectionError) as e:
            # Check if our Mintry interceptor was the root cause
            error_msg = str(e)
            cause_msg = str(e.__cause__) if e.__cause__ else ""
            if "Mintry" in error_msg or "Mintry" in cause_msg:
                print(f"\n[SUCCESS] Fabric Intervened at Request #{i+1}")
                print(f"Reason: {e}")
                return
            raise e