"""Async notification delivery for alerts and digests (off the enforcement hot path)."""

from __future__ import annotations

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
