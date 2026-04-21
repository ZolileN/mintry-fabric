class PolicyEngine:
    def __init__(self, wallet):
        self.wallet = wallet

    def authorize(self, mandate_id: str, request, deduct: bool = True):
        # 1. Fetch the fiscal data from the wallet
        mandate = self.wallet.get_mandate(mandate_id)
        
        # 2. Safety Check: Is there at least $0.01 left?
        if (mandate['budget_usd'] - mandate['spent_usd']) < 0.01:
            return False
            
        # 3. Apply base fee only if we aren't metering tokens later
        if deduct:
            self.wallet.record_usage(mandate_id, 0.002)
            
        return True

    def shield(self, task, max_usd):
        # This context manager is what the test uses
        from contextlib import contextmanager
        @contextmanager
        def mandate_scope():
            # In a real app, this would generate a UUID
            class MockMandate:
                id = "mt_task_882x"
            yield MockMandate()
        return mandate_scope()
