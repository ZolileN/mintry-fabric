"""Periodic spend digest notifications (async analytics layer)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from mintry.core.notifications import NotificationDispatcher

logger = logging.getLogger(__name__)

DEFAULT_DIGEST_INTERVAL_SEC = 604800.0  # 7 days


class DigestWorker:
    """Posts a summary digest when enabled — never on the authorize hot path."""

    def __init__(
        self,
        wallet: Any,
        dispatcher: NotificationDispatcher,
        interval_sec: float = DEFAULT_DIGEST_INTERVAL_SEC,
    ) -> None:
        self._wallet = wallet
        self._dispatcher = dispatcher
        self._interval_sec = max(interval_sec, 3600.0)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="mintry-digest")
        self._thread.start()
        logger.info("Digest worker started (interval=%.0fs)", self._interval_sec)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._stop.wait(timeout=self._interval_sec):
                break
            try:
                self._send_digest()
            except Exception as exc:
                logger.error("Digest worker error: %s", exc)

    def _send_digest(self) -> None:
        conn = self._wallet.conn
        rows = conn.execute(
            "SELECT id, max_usd, spent_usd, status FROM mandates ORDER BY spent_usd DESC"
        ).fetchall()
        if not rows:
            return

        total_spent = sum(r[2] or 0.0 for r in rows)
        total_budget = sum(r[1] or 0.0 for r in rows)
        active = sum(1 for r in rows if r[3] == "active")
        top = rows[0][0] if rows else "none"

        summary = (
            "nothing needs your attention"
            if total_spent < total_budget * 0.8
            else "review budgets — utilization is elevated"
        )

        self._dispatcher.dispatch_async({
            "event": "spend_digest",
            "total_spent_usd": round(total_spent, 4),
            "total_budget_usd": round(total_budget, 4),
            "active_agents": active,
            "top_consumer": top,
            "summary": summary,
        })
