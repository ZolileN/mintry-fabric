"""Stripe settlement bridge — control-plane budget top-ups (never on authorize hot path)."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StripeTopUpBridge:
    """Apply Stripe checkout completions as ledger budget increases."""

    def apply_top_up(
        self,
        wallet: Any,
        mandate_id: str,
        amount_usd: Decimal,
        *,
        stripe_event_id: Optional[str] = None,
    ) -> dict:
        existing = wallet.get_mandate(mandate_id)
        if existing.get("status") == "unknown":
            wallet.create_mandate(mandate_id, float(amount_usd))
        wallet.add_funds(mandate_id, amount_usd)
        details = "Stripe checkout completed"
        if stripe_event_id:
            details = f"Stripe checkout completed ({stripe_event_id})"
        wallet.log_decision(mandate_id, "top_up", float(amount_usd), details)
        updated = wallet.get_mandate(mandate_id)
        logger.info("Stripe top-up applied: %s +$%s", mandate_id, amount_usd)
        return {
            "mandate_id": mandate_id,
            "budget_usd": updated.get("budget_usd"),
            "spent_usd": updated.get("spent_usd"),
        }

    def parse_checkout_completed(self, event: dict) -> Optional[tuple[str, Decimal]]:
        """Extract (mandate_id, amount_usd) from a Stripe checkout.session.completed event."""
        if event.get("type") != "checkout.session.completed":
            return None
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata") or {}
        mandate_id = metadata.get("mandate_id") or metadata.get("mintry_mandate_id")
        if not mandate_id:
            return None
        amount_total = session.get("amount_total")
        if amount_total is None:
            return None
        # Stripe amounts are in cents
        amount_usd = Decimal(str(amount_total)) / Decimal("100")
        return mandate_id, amount_usd

    @staticmethod
    def parse_json_event(raw: bytes) -> dict:
        return json.loads(raw.decode("utf-8"))
