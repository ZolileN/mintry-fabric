import uuid
from contextlib import contextmanager


class Mandate:
    """Represents an active budget mandate for a scoped task."""

    def __init__(self, mandate_id: str, task: str, max_usd: float):
        self.id = mandate_id
        self.task = task
        self.max_usd = max_usd

    def __repr__(self):
        return f"Mandate(id={self.id!r}, task={self.task!r}, max_usd={self.max_usd})"


class PolicyEngine:
    def __init__(self, wallet):
        self.wallet = wallet
        self.api_key = None

    def authorize(self, mandate_id: str, request, deduct: bool = True):
        """
        Performs a two-phase budget check for an outbound request.

        Phase 1 — Safety threshold: ensures at least $0.01 headroom.
        Phase 2 — Base fee deduction (if deduct=True).

        Returns True if authorized, False if budget is exhausted.
        """
        mandate = self.wallet.get_mandate(mandate_id)
        remaining = mandate['budget_usd'] - mandate['spent_usd']

        if remaining < 0.01:
            return False

        # Apply base fee only if we aren't metering tokens post-flight
        if deduct:
            self.wallet.record_usage(mandate_id, 0.002)

        return True

    def get_budget_summary(self, mandate_id: str) -> dict:
        """Returns a budget summary with remaining headroom for error messages."""
        mandate = self.wallet.get_mandate(mandate_id)
        remaining = mandate['budget_usd'] - mandate['spent_usd']
        return {
            "mandate_id": mandate_id,
            "budget_usd": mandate['budget_usd'],
            "spent_usd": mandate['spent_usd'],
            "remaining_usd": round(remaining, 6),
        }

    @contextmanager
    def shield(self, task: str, max_usd: float):
        """
        Context manager that creates a scoped mandate for a single task.

        On entry: creates a new mandate with a UUID-based ID and the given budget.
        On exit: marks the mandate as exhausted.

        Usage:
            with engine.shield("analyze-logs", max_usd=0.10) as mandate:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[...],
                    extra_headers={"X-Mintry-Mandate": mandate.id}
                )
        """
        mandate_id = f"mt_{uuid.uuid4().hex[:12]}"
        self.wallet.create_mandate(mandate_id, float(max_usd))
        mandate = Mandate(mandate_id=mandate_id, task=task, max_usd=float(max_usd))

        try:
            yield mandate
        finally:
            self.wallet.exhaust_mandate(mandate_id)
