"""Tests for background-first unified plan: attribution, telemetry, metering, alerts."""

import json
import time
import threading
import pytest
import httpx

import mintry
from mintry.interceptors.global_http import GlobalHTTPInterceptor, _extract_tokens
from mintry.core.mandate_context import resolve_default_mandate_id, resolve_default_budget_usd
from mintry.core.alert_monitor import BudgetAlertMonitor


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path, monkeypatch):
    GlobalHTTPInterceptor._reset()
    mintry._global_engine = None
    monkeypatch.setenv("MINTRY_AGENT_ID", "default_agent")
    monkeypatch.setenv("MINTRY_DEFAULT_BUDGET_USD", "50.0")
    yield
    GlobalHTTPInterceptor._reset()
    mintry._global_engine = None


def test_extract_tokens_anthropic_shape():
    data = {
        "model": "claude-sonnet-4-20250514",
        "usage": {"input_tokens": 1200, "output_tokens": 300},
    }
    prompt, completion = _extract_tokens(data)
    assert prompt == 1200
    assert completion == 300


def test_mandate_context_auto_attribution(tmp_path, httpx_mock):
    """mintry.mandate() attributes nested httpx calls without manual headers."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    mock_response = {
        "id": "chatcmpl-ctx",
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    }
    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json=mock_response,
        status_code=200,
    )

    with mintry.mandate("research_task", cap=10.0):
        with httpx.Client() as client:
            client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
            )

    from mintry.interceptors.global_http import _flush_metering_queue
    _flush_metering_queue()

    spent = fabric.wallet.get_spent("research_task")
    assert spent > 0.0


def test_default_mandate_not_trap(tmp_path):
    db = str(tmp_path / "vouchers.db")
    mintry.init(api_key="test_key_2026", db_path=db)
    from mintry.core.wallet import MintryWallet

    wallet = MintryWallet(db_path=db)
    default_id = resolve_default_mandate_id()
    row = wallet.get_mandate(default_id)
    assert row["budget_usd"] >= 1.0
    assert row["budget_usd"] == resolve_default_budget_usd()


def test_telemetry_recorded_on_authorize(tmp_path, monkeypatch):
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    recorded = []

    class FakeBatcher:
        def record_decision(self, mandate_id, action, amount, details, agent_id=None):
            recorded.append((mandate_id, action, amount, details, agent_id))

    fabric.telemetry_batcher = FakeBatcher()
    fabric.authorize("default_agent", object(), deduct=False)
    assert any(r[1] == "allow" for r in recorded)


def test_budget_threshold_alert_once(tmp_path):
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    fabric.wallet.create_mandate("alert_agent", 10.0)

    payloads = []
    fabric._dispatch_webhook = lambda p: payloads.append(p)
    monitor = BudgetAlertMonitor(fabric)

    monitor._check("alert_agent", 10.0, 8.5)
    monitor._check("alert_agent", 10.0, 8.6)
    threshold_events = [p for p in payloads if p.get("event") == "budget_threshold"]
    assert len(threshold_events) == 1
    assert threshold_events[0]["threshold_pct"] == 80


def test_mintry_mandate_uses_stable_task_id(tmp_path):
    """Top-level mandate() keeps readable ledger ids for dashboard visibility."""
    db = str(tmp_path / "vouchers.db")
    mintry.init(api_key="test_key_2026", db_path=db)

    with mintry.mandate("task:nightly_summarizer", cap=50.00) as m:
        assert m.id == "task:nightly_summarizer"
        assert m.max_usd == 50.00

    row = mintry._global_engine.wallet.get_mandate("task:nightly_summarizer")
    assert row["status"] == "active"
    assert row["budget_usd"] == 50.00
