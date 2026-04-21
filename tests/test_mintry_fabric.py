import mintry
from decimal import Decimal
from openai import OpenAI, AuthenticationError, APIConnectionError  # <-- Add APIConnectionError here

def test_logic_fabric_enforcement():
    fabric = mintry.init(api_key="test_key_2026")
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
            # We look at the error message or the __cause__ (chained exception)
            error_msg = str(e)
            if "Mintry" in error_msg or (hasattr(e, '__cause__') and "Mintry" in str(e.__cause__)):
                print(f"\n[SUCCESS] Fabric Intervened at Request #{i+1}")
                print(f"Reason: {e}")
                return
            raise e