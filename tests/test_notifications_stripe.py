"""Tests for notifications, digest, Stripe top-up bridge."""

import time
from decimal import Decimal

import pytest

from mintry.core.notifications import NotificationDispatcher, _slack_payload
from mintry.core.digest_worker import DigestWorker
from mintry.bridge.stripe_webhook import StripeTopUpBridge
from mintry.core.wallet import MintryWallet


def test_slack_payload_threshold():
    payload = _slack_payload({
        "event": "budget_threshold",
        "mandate_id": "agent_a",
        "threshold_pct": 80,
        "spent_usd": 8.0,
        "budget_usd": 10.0,
    })
    assert "agent_a" in payload["text"]
    assert "80%" in payload["text"]


def test_notification_dispatcher_channels(monkeypatch):
    monkeypatch.setenv("MINTRY_WEBHOOK_URL", "http://example.com/hook")
    d = NotificationDispatcher()
    channels = d.channels_configured()
    assert channels["webhook"] is True
    assert channels["slack"] is False


def test_stripe_parse_checkout_completed():
    bridge = StripeTopUpBridge()
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"mandate_id": "research_agent"},
                "amount_total": 2500,
            },
        },
    }
    parsed = bridge.parse_checkout_completed(event)
    assert parsed == ("research_agent", Decimal("25"))


def test_topup_api(tmp_path, monkeypatch):
    from mintry.core.dashboard import DashboardHandler

    monkeypatch.setenv("MINTRY_DASHBOARD_API_TOKEN", "test-token")
    temp_db = str(tmp_path / "topup.db")
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("stripe_agent", 10.0)

    DashboardHandler.db_path = temp_db
    handler = DashboardHandler.__new__(DashboardHandler)

    body = b'{"mandate_id":"stripe_agent","amount_usd":5.0,"source":"stripe"}'
    handler.headers = type("H", (), {
        "get": lambda self, key, default=None: (
            "Bearer test-token" if key == "Authorization" else
            str(len(body)) if key == "Content-Length" else default
        ),
    })()
    handler.rfile = type("R", (), {"read": lambda self, n: body})()
    handler.send_json_response = lambda data, code: setattr(handler, "_last", (data, code))
    handler.send_error = lambda *a: None
    handler.path = "/api/topup"
    handler.do_POST()

    updated = wallet.get_mandate("stripe_agent")
    assert updated["budget_usd"] == 15.0


def test_digest_worker_sends(tmp_path):
    temp_db = str(tmp_path / "digest.db")
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("digest_agent", 100.0)
    wallet.record_usage("digest_agent", 10.0)

    sent = []
    class FakeDispatcher:
        def dispatch_async(self, payload):
            sent.append(payload)

    worker = DigestWorker(wallet, FakeDispatcher(), interval_sec=3600)
    worker._send_digest()
    assert sent
    assert sent[0]["event"] == "spend_digest"
