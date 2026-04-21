import mintry
from decimal import Decimal
from openai import OpenAI, AuthenticationError, APIConnectionError
from mintry.bridge.stripe_mpp import MockStripeBridge

def test_mpp_resurrection():
    fabric = mintry.init(api_key="test_key_2026")
    client = OpenAI(api_key="sk-mock-key")
    bridge = MockStripeBridge()
    mandate_id = "mt_task_882x"

    print("\n--- Phase 1: Verify Blocked State ---")
    try:
        client.chat.completions.create(model="gpt-5", messages=[{"role":"user","content":"hi"}])
    except (PermissionError, APIConnectionError):
        print("Confirmed: Agent is currently grounded.")

    print("\n--- Phase 2: Stripe MPP Settlement ---")
    # Simulate a user paying $5.00 via Stripe
    bridge.trigger_top_up(fabric.wallet, mandate_id, Decimal("5.00"))

    print("\n--- Phase 3: Verify Unblocked State ---")
    # This should no longer raise a PermissionError! 
    # It should pass through to AuthenticationError (because of the mock key)
    try:
        client.chat.completions.create(model="gpt-5", messages=[{"role":"user","content":"hi"}])
        print("Success: Agent has resumed operations.")
    except AuthenticationError:
        print("Success: Fabric allowed the request (Failed at OpenAI as expected).")
    except Exception as e:
        pytest.fail(f"Fabric should have allowed this request, but got: {type(e).__name__}")
