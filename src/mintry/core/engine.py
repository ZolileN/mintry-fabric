import uuid
import os
import threading
import httpx
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Any


class Mandate:
    """Represents an active budget mandate for a scoped task."""

    def __init__(self, mandate_id: str, task: str, max_usd: float):
        self.id = mandate_id
        self.task = task
        self.max_usd = max_usd

    def __repr__(self):
        return f"Mandate(id={self.id!r}, task={self.task!r}, max_usd={self.max_usd})"


class PolicyEngine:
    # Policy sync infrastructure (dynamically attached by mintry.init())
    policy_cache: Optional[Any] = None
    control_plane: Optional[Any] = None
    telemetry_batcher: Optional[Any] = None

    def __init__(self, wallet, webhook_url: Optional[str] = None):
        self.wallet = wallet
        self.api_key = None
        self.webhook_url = webhook_url or os.environ.get("MINTRY_WEBHOOK_URL")

    def _dispatch_webhook(self, payload: dict):
        """Dispatches a webhook POST request asynchronously in a background thread."""
        if not self.webhook_url:
            return
        
        def _send():
            try:
                with httpx.Client(timeout=2.0) as client:
                    client.post(self.webhook_url, json=payload)
            except Exception:
                pass
                
        threading.Thread(target=_send, daemon=True).start()

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
            mandate = self.wallet.get_mandate(mandate_id)
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                f"Mandate expired — request rejected"
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "expired",
                "mandate_id": mandate_id,
                "budget_usd": mandate.get("budget_usd", 0.0),
                "spent_usd": mandate.get("spent_usd", 0.0),
            })
            return False

        # Phase 2: Budget check
        mandate = self.wallet.get_mandate(mandate_id)

        # Reject exhausted mandates
        if mandate.get("status") == "exhausted":
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                f"Budget exhausted (${mandate.get('spent_usd', 0):.4f} / ${mandate.get('budget_usd', 0):.4f})"
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "budget_exhausted",
                "mandate_id": mandate_id,
                "budget_usd": mandate.get("budget_usd", 0.0),
                "spent_usd": mandate.get("spent_usd", 0.0),
            })
            return False

        remaining = mandate['budget_usd'] - mandate['spent_usd']
        if remaining < 0.01:
            self.wallet.log_decision(
                mandate_id, "block", round(remaining, 4),
                f"Insufficient headroom (${remaining:.4f} remaining)"
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "budget_exhausted",
                "mandate_id": mandate_id,
                "budget_usd": mandate.get("budget_usd", 0.0),
                "spent_usd": mandate.get("spent_usd", 0.0),
            })
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
    def shield(self, task: str, max_usd: Optional[float] = None, expires_at: Optional[datetime] = None):
        """
        Context manager that creates or resolves a scoped mandate for a task.

        If max_usd is None, it resolves against pre-allocated dashboard mandates.
        On exit of a standard scoped mandate, marks it as exhausted.
        """
        is_shared = False
        existing = self.wallet.get_mandate(task)
        
        if max_usd is None:
            if existing.get("status") != "unknown":
                mandate_id = task
                max_usd = existing.get("budget_usd", 0.0)
                is_shared = True
            else:
                # Auto-discovery fallback: create a default base mandate
                mandate_id = task
                max_usd = 0.05
                self.wallet.create_mandate(mandate_id, max_usd, expires_at=expires_at)
                is_shared = True
        else:
            mandate_id = f"mt_{uuid.uuid4().hex[:12]}"
            self.wallet.create_mandate(mandate_id, float(max_usd), expires_at=expires_at)

        mandate = Mandate(mandate_id=mandate_id, task=task, max_usd=float(max_usd))

        try:
            yield mandate
        finally:
            if not is_shared:
                self.wallet.exhaust_mandate(mandate_id)
                mandate_info = self.wallet.get_mandate(mandate_id)
                self._dispatch_webhook({
                    "event": "mandate_exhausted",
                    "mandate_id": mandate_id,
                    "budget_usd": mandate_info.get("budget_usd", 0.0),
                    "spent_usd": mandate_info.get("spent_usd", 0.0),
                })
