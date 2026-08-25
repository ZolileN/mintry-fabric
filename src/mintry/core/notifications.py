"""Proactive budget notices — the "we tell you before it bites" layer.

Everything here runs *after* a request has already been authorized, executed and
metered. Notices are evaluated by the metering worker thread and delivered on a
separate background thread, so no request's latency depends on a notice being
computed or delivered (Principle 3).

A notice is deterministic: it fires when observed spend crosses a utilization
threshold the customer configured. It never changes an allow/block decision —
`BudgetWatch` has no write access to caps and is not consulted by
`PolicyEngine.authorize` (Principle 6).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional


DEFAULT_THRESHOLDS: tuple[float, ...] = (0.5, 0.8, 0.95)

# Trailing window used to estimate a burn rate for the runway forecast.
_BURN_RATE_WINDOW_HOURS = 6.0


def parse_thresholds(raw: Optional[str]) -> tuple[float, ...]:
    """Parse a comma-separated threshold list.

    Accepts percentages (``"50,80,95"``) or fractions (``"0.5,0.8,0.95"``);
    values above 1 are treated as percentages. Invalid entries are dropped so a
    malformed env var degrades to the default rather than breaking startup.
    """
    if not raw:
        return DEFAULT_THRESHOLDS

    parsed: set[float] = set()
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = float(chunk)
        except ValueError:
            continue
        if value > 1.0:
            value = value / 100.0
        if 0.0 < value <= 1.0:
            parsed.add(round(value, 4))

    if not parsed:
        return DEFAULT_THRESHOLDS
    return tuple(sorted(parsed))


def resolve_thresholds(explicit: Optional[Iterable[float]] = None) -> tuple[float, ...]:
    """Resolve notice thresholds from an explicit argument then the environment."""
    if explicit is not None:
        normalized = parse_thresholds(",".join(str(t) for t in explicit))
        return normalized
    return parse_thresholds(os.environ.get("MINTRY_BUDGET_ALERT_THRESHOLDS"))


class BudgetNotice:
    """A single threshold crossing for one mandate."""

    __slots__ = (
        "mandate_id",
        "threshold",
        "budget_usd",
        "spent_usd",
        "utilization",
        "remaining_usd",
        "burn_rate_usd_per_hour",
        "projected_exhaustion_at",
        "observed_at",
    )

    def __init__(
        self,
        mandate_id: str,
        threshold: float,
        budget_usd: float,
        spent_usd: float,
        burn_rate_usd_per_hour: Optional[float] = None,
        projected_exhaustion_at: Optional[str] = None,
        observed_at: Optional[str] = None,
    ):
        self.mandate_id = mandate_id
        self.threshold = round(float(threshold), 4)
        self.budget_usd = round(float(budget_usd), 6)
        self.spent_usd = round(float(spent_usd), 6)
        self.utilization = (
            round(float(spent_usd) / float(budget_usd), 6) if budget_usd > 0 else 0.0
        )
        self.remaining_usd = round(float(budget_usd) - float(spent_usd), 6)
        self.burn_rate_usd_per_hour = burn_rate_usd_per_hour
        self.projected_exhaustion_at = projected_exhaustion_at
        self.observed_at = observed_at or datetime.now(timezone.utc).isoformat()

    def headline(self) -> str:
        return (
            f"{self.mandate_id} has used {self.utilization * 100:.0f}% of its "
            f"${self.budget_usd:,.2f} budget"
        )

    def to_payload(self) -> dict:
        return {
            "event": "budget_threshold_crossed",
            "mandate_id": self.mandate_id,
            "threshold": self.threshold,
            "utilization": self.utilization,
            "budget_usd": self.budget_usd,
            "spent_usd": self.spent_usd,
            "remaining_usd": self.remaining_usd,
            "burn_rate_usd_per_hour": self.burn_rate_usd_per_hour,
            "projected_exhaustion_at": self.projected_exhaustion_at,
            "observed_at": self.observed_at,
            "headline": self.headline(),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"BudgetNotice(mandate_id={self.mandate_id!r}, "
            f"threshold={self.threshold}, utilization={self.utilization})"
        )


def project_exhaustion(
    remaining_usd: float, burn_rate_usd_per_hour: Optional[float], now: Optional[datetime] = None
) -> Optional[str]:
    """Project when a mandate runs out at the observed burn rate.

    Returns ``None`` when there is no measurable burn rate — an honest "unknown"
    beats an invented date.
    """
    if not burn_rate_usd_per_hour or burn_rate_usd_per_hour <= 0:
        return None
    if remaining_usd <= 0:
        return (now or datetime.now(timezone.utc)).isoformat()

    hours = remaining_usd / burn_rate_usd_per_hour
    # Cap the horizon so a near-idle agent doesn't report a date centuries out.
    if hours > 24 * 365:
        return None
    return ((now or datetime.now(timezone.utc)) + timedelta(hours=hours)).isoformat()


class BudgetWatch:
    """Detects budget threshold crossings and hands them to a dispatcher.

    Dedupe is keyed on ``(mandate_id, threshold, budget)``, so raising a cap
    re-arms every threshold: a topped-up mandate warns again on the way to its
    new ceiling. Crossings are persisted append-only by the wallet, so a process
    restart does not re-send notices the tenant already received.
    """

    def __init__(
        self,
        wallet,
        thresholds: Optional[Iterable[float]] = None,
        dispatch: Optional[Callable[[dict], None]] = None,
        burn_rate_window_hours: float = _BURN_RATE_WINDOW_HOURS,
    ):
        self.wallet = wallet
        self.thresholds = resolve_thresholds(thresholds)
        self._dispatch = dispatch
        self._burn_rate_window_hours = burn_rate_window_hours
        self._sent: set[tuple[str, float, float]] = set()
        self._hydrated = False

    # ── internals ────────────────────────────────────────────────────

    @staticmethod
    def _key(mandate_id: str, threshold: float, budget_usd: float) -> tuple[str, float, float]:
        return (mandate_id, round(float(threshold), 4), round(float(budget_usd), 4))

    def _hydrate(self) -> None:
        """Load previously delivered notices so restarts don't re-notify."""
        if self._hydrated:
            return
        self._hydrated = True
        lister = getattr(self.wallet, "delivered_budget_notices", None)
        if lister is None:
            return
        try:
            for mandate_id, threshold, budget_usd in lister():
                self._sent.add(self._key(mandate_id, threshold, budget_usd))
        except Exception:
            # A cold cache only risks a duplicate notice, never a missed one.
            pass

    def _burn_rate(self, mandate_id: str) -> Optional[float]:
        reader = getattr(self.wallet, "spend_in_window", None)
        if reader is None:
            return None
        try:
            spent = reader(mandate_id, self._burn_rate_window_hours)
        except Exception:
            return None
        if not spent or spent <= 0:
            return None
        return round(float(spent) / self._burn_rate_window_hours, 8)

    # ── public API ───────────────────────────────────────────────────

    def crossed(self, spent_usd: float, budget_usd: float) -> list[float]:
        """Return every configured threshold that ``spent/budget`` has reached."""
        if budget_usd <= 0:
            return []
        utilization = float(spent_usd) / float(budget_usd)
        return [t for t in self.thresholds if utilization >= t]

    def observe(self, mandate_id: str, spent_usd: float, budget_usd: float) -> list[BudgetNotice]:
        """Evaluate one mandate and return notices that are newly due.

        Pure bookkeeping plus (optionally) a burn-rate read; safe to call from
        any background worker. Only the highest newly-crossed threshold produces
        a notice, so a large single charge that jumps 50% → 95% sends one alert
        rather than three.
        """
        if budget_usd <= 0:
            return []

        self._hydrate()
        due = [t for t in self.crossed(spent_usd, budget_usd)
               if self._key(mandate_id, t, budget_usd) not in self._sent]
        if not due:
            return []

        # Mark every crossed threshold as sent, but only announce the highest.
        highest = max(due)
        for threshold in due:
            self._sent.add(self._key(mandate_id, threshold, budget_usd))

        burn_rate = self._burn_rate(mandate_id)
        notice = BudgetNotice(
            mandate_id=mandate_id,
            threshold=highest,
            budget_usd=budget_usd,
            spent_usd=spent_usd,
            burn_rate_usd_per_hour=burn_rate,
            projected_exhaustion_at=project_exhaustion(
                float(budget_usd) - float(spent_usd), burn_rate
            ),
        )
        return [notice]

    def evaluate(self, mandate_id: str, budget_usd: Optional[float] = None) -> list[BudgetNotice]:
        """Observe a mandate, then record and dispatch any notice that is due."""
        try:
            mandate = self.wallet.get_mandate(mandate_id)
        except Exception:
            return []

        spent = float(mandate.get("spent_usd", 0.0) or 0.0)
        budget = float(
            budget_usd if budget_usd is not None else mandate.get("budget_usd", 0.0) or 0.0
        )

        notices = self.observe(mandate_id, spent, budget)
        for notice in notices:
            self._record(notice)
            self._deliver(notice)
        return notices

    def _record(self, notice: BudgetNotice) -> None:
        recorder = getattr(self.wallet, "record_budget_notice", None)
        if recorder is None:
            return
        try:
            recorder(
                notice.mandate_id,
                notice.threshold,
                notice.budget_usd,
                notice.spent_usd,
                notice.projected_exhaustion_at,
            )
        except Exception:
            pass

    def _deliver(self, notice: BudgetNotice) -> None:
        if self._dispatch is None:
            return
        try:
            self._dispatch(notice.to_payload())
        except Exception:
            pass


import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: float = 5.0) -> bool:
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("Notification POST failed HTTP %s to %s", exc.code, url)
        return False
    except Exception as exc:
        logger.warning("Notification POST error to %s: %s", url, exc)
        return False


def _slack_payload(event: dict) -> dict:
    mandate = event.get("mandate_id", "unknown")
    kind = event.get("event", "mintry_alert")
    if kind == "budget_threshold":
        text = (
            f"Mintry budget alert: `{mandate}` at {event.get('threshold_pct')}% "
            f"(${event.get('spent_usd'):.4f} / ${event.get('budget_usd'):.4f})"
        )
    elif kind == "spend_digest":
        text = (
            f"Mintry weekly digest: ${event.get('total_spent_usd'):.2f} spent across "
            f"{event.get('active_agents', 0)} agents — {event.get('summary', '')}"
        )
    else:
        text = f"Mintry: {kind} for `{mandate}` — {json.dumps(event)}"
    return {"text": text}


class NotificationDispatcher:
    """Deliver alert/digest events to configured channels (async only)."""

    def dispatch_async(self, payload: Dict[str, Any]) -> None:
        threading.Thread(
            target=self._dispatch,
            args=(payload,),
            daemon=True,
            name="mintry-notify",
        ).start()

    def _dispatch(self, payload: Dict[str, Any]) -> None:
        webhook = os.environ.get("MINTRY_WEBHOOK_URL", "").strip()
        slack = os.environ.get("MINTRY_SLACK_WEBHOOK_URL", "").strip()
        resend_key = os.environ.get("MINTRY_RESEND_API_KEY", "").strip()
        email_to = os.environ.get("MINTRY_ALERT_EMAIL_TO", "").strip()

        if webhook:
            _post_json(webhook, payload)

        if slack:
            _post_json(slack, _slack_payload(payload))

        if resend_key and email_to:
            subject = f"Mintry alert: {payload.get('event', 'notification')}"
            body = json.dumps(payload, indent=2)
            _post_json(
                "https://api.resend.com/emails",
                {
                    "from": os.environ.get("MINTRY_ALERT_EMAIL_FROM", "alerts@mintry.local"),
                    "to": [email_to],
                    "subject": subject,
                    "text": body,
                },
                headers={"Authorization": f"Bearer {resend_key}"},
            )

    def channels_configured(self) -> dict:
        return {
            "webhook": bool(os.environ.get("MINTRY_WEBHOOK_URL")),
            "slack": bool(os.environ.get("MINTRY_SLACK_WEBHOOK_URL")),
            "email": bool(
                os.environ.get("MINTRY_RESEND_API_KEY")
                and os.environ.get("MINTRY_ALERT_EMAIL_TO")
            ),
        }
