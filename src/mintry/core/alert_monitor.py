"""Async budget threshold alerts — off the enforcement hot path."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Utilization thresholds (percent) that trigger one-shot webhook alerts per mandate.
_DEFAULT_THRESHOLDS: Tuple[int, ...] = (80, 95, 100)


class BudgetAlertMonitor:
    """Fire threshold webhooks once per mandate per threshold crossing."""

    def __init__(
        self,
        engine: Any,
        thresholds: Tuple[int, ...] = _DEFAULT_THRESHOLDS,
    ) -> None:
        self._engine = engine
        self._thresholds = thresholds
        self._fired: Set[Tuple[str, int]] = set()
        self._lock = threading.Lock()

    def check_async(self, mandate_id: str, budget_usd: float, spent_usd: float) -> None:
        """Schedule a utilization check on a background thread."""
        if budget_usd <= 0:
            return
        threading.Thread(
            target=self._check,
            args=(mandate_id, budget_usd, spent_usd),
            daemon=True,
            name="mintry-budget-alert",
        ).start()

    def _check(self, mandate_id: str, budget_usd: float, spent_usd: float) -> None:
        utilization = (spent_usd / budget_usd) * 100.0
        for threshold in self._thresholds:
            if utilization < threshold:
                continue
            key = (mandate_id, threshold)
            with self._lock:
                if key in self._fired:
                    continue
                self._fired.add(key)

            payload: Dict[str, Any] = {
                "event": "budget_threshold",
                "mandate_id": mandate_id,
                "threshold_pct": threshold,
                "budget_usd": round(budget_usd, 6),
                "spent_usd": round(spent_usd, 6),
                "utilization_pct": round(utilization, 2),
            }
            dispatch = getattr(self._engine, "_dispatch_webhook", None)
            if dispatch:
                dispatch(payload)
            logger.info(
                "Budget threshold alert: %s at %d%% (spent=%.4f budget=%.4f)",
                mandate_id,
                threshold,
                spent_usd,
                budget_usd,
            )
