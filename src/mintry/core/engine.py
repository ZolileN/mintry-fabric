import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional


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
        Performs a three-phase budget check for an outbound request.

        Phase 1 — Expiry check: rejects expired mandates.
        Phase 2 — Safety threshold: ensures at least $0.01 headroom.
        Phase 3 — Base fee deduction (if deduct=True).

        Returns True if authorized, False if budget is exhausted or mandate expired.
        """
        # Phase 1: Expiry check
        if self.wallet.is_expired(mandate_id):
            return False

        # Phase 2: Budget check
        mandate = self.wallet.get_mandate(mandate_id)

        # Reject exhausted mandates
        if mandate.get("status") == "exhausted":
            return False

        remaining = mandate['budget_usd'] - mandate['spent_usd']
        if remaining < 0.01:
            return False

        # Phase 3: Apply base fee only if we aren't metering tokens post-flight
        if deduct:
            self.wallet.record_usage(mandate_id, 0.002)

        return True

    def get_budget_summary(self, mandate_id: str) -> dict:
        """Returns a budget summary with remaining headroom for error messages."""
        mandate = self.wallet.get_mandate(mandate_id)
        remaining = mandate['budget_usd'] - mandate['spent_usd']
        is_expired = self.wallet.is_expired(mandate_id)
        return {
            "mandate_id": mandate_id,
            "budget_usd": mandate['budget_usd'],
            "spent_usd": mandate['spent_usd'],
            "remaining_usd": round(remaining, 6),
            "status": mandate.get("status", "unknown"),
            "expired": is_expired,
        }

    @contextmanager
    def shield(self, task: str, max_usd: float, expires_at: Optional[datetime] = None):
        """
        Context manager that creates a scoped mandate for a single task.

        On entry: creates a new mandate with a UUID-based ID and the given budget.
        On exit: marks the mandate as exhausted.

        Args:
            task: Human-readable task description.
            max_usd: Budget ceiling for this task scope.
            expires_at: Optional expiry timestamp. If set, the mandate will be
                       rejected after this time.

        Usage:
            with engine.shield("analyze-logs", max_usd=0.10) as mandate:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[...],
                    extra_headers={"X-Mintry-Mandate": mandate.id}
                )
        """
        mandate_id = f"mt_{uuid.uuid4().hex[:12]}"
        self.wallet.create_mandate(mandate_id, float(max_usd), expires_at=expires_at)
        mandate = Mandate(mandate_id=mandate_id, task=task, max_usd=float(max_usd))

        try:
            yield mandate
        finally:
            self.wallet.exhaust_mandate(mandate_id)
