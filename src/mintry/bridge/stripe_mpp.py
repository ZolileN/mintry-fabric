from decimal import Decimal
import uuid

class MockStripeBridge:
    """Simulates the 2026 Mintry Payment Protocol bridge."""
    
    def trigger_top_up(self, wallet, mandate_id: str, amount: Decimal):
        """
        Simulates a successful Stripe webhook hit.
        In production, this would be triggered by a Stripe 'checkout.session.completed' event.
        """
        print(f"\n[STRIPE MOCK] Processing settlement for {mandate_id}: ${amount}")
        
        # The bridge communicates directly with the wallet substrate
        success = wallet.add_funds(mandate_id, amount)
        
        if success:
            txn_id = f"mpp_{uuid.uuid4().hex[:8]}"
            print(f"[STRIPE MOCK] Funds settled. Transaction ID: {txn_id}")
            return txn_id
        return None
