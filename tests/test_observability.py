"""Integration and unit tests for v0.5.0 Observability features."""

import os
import json
import pytest
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
import httpx
from http.server import HTTPServer

from mintry.core.wallet import MintryWallet
from mintry.core.engine import PolicyEngine
from mintry.interceptors.global_http import GlobalHTTPInterceptor, _print_log
from mintry.core.dashboard import DashboardHandler, start_dashboard


@pytest.fixture
def temp_db(tmp_path):
    """Provides a temporary SQLite database path."""
    return str(tmp_path / "test_observability.db")


# ── JSON Logging Tests ───────────────────────────────────────────────

def test_json_logging_format(capsys, monkeypatch):
    """Verify that _print_log outputs correctly formatted JSON when MINTRY_JSON_LOGS=1."""
    monkeypatch.setenv("MINTRY_JSON_LOGS", "1")
    
    _print_log("test_event", detail_msg="hello world", amount=1.25)
    
    captured = capsys.readouterr()
    log_line = captured.out.strip()
    
    # Assert it is valid JSON
    data = json.loads(log_line)
    assert data["event"] == "test_event"
    assert data["detail_msg"] == "hello world"
    assert data["amount"] == 1.25
    assert "timestamp" in data


# ── Webhook Alert Tests ──────────────────────────────────────────────

def test_webhook_alert_dispatch(temp_db, httpx_mock, monkeypatch):
    """Verify webhooks are dispatched on authorization failure or shield completion."""
    wallet = MintryWallet(db_path=temp_db)
    engine = PolicyEngine(wallet, webhook_url="http://mintry-webhook.local/alerts")

    # Force webhook dispatch to run synchronously to avoid async/thread timing issues in test
    def mock_thread_start(self):
        self._target(*self._args, **self._kwargs)
    
    monkeypatch.setattr(threading.Thread, "start", mock_thread_start)

    # Mock the webhook endpoint
    httpx_mock.add_response(
        url="http://mintry-webhook.local/alerts",
        method="POST",
        status_code=200
    )

    # 1. Test Shield Completion Event
    with engine.shield("test-task", max_usd=1.0) as mandate:
        pass  # triggers exhaust on exit

    # Verify webhook request was captured
    request = httpx_mock.get_request()
    assert request is not None
    payload = json.loads(request.read())
    assert payload["event"] == "mandate_exhausted"
    assert payload["mandate_id"] == mandate.id
    assert payload["budget_usd"] == 1.0


# ── Dashboard API & Server Tests ──────────────────────────────────────

def test_dashboard_api_stats(temp_db):
    """Verify that the dashboard helper retrieves correct database metrics and history."""
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("dash_01", 10.0)
    wallet.add_funds("dash_01", Decimal("5.0"))
    wallet.record_usage("dash_01", 1.50)
    
    wallet.create_mandate("dash_02", 2.0)
    wallet.exhaust_mandate("dash_02")

    # Access API summary generator directly via a temporary handler configuration
    DashboardHandler.db_path = temp_db
    handler = DashboardHandler.__new__(DashboardHandler)
    handler.db_path = temp_db
    
    stats_data = handler.get_stats_data()
    
    # Assert KPIs
    assert stats_data["stats"]["total_mandates"] == 3  # seed mandate + 2 new
    assert stats_data["stats"]["total_spent"] >= 1.50   # 1.50 + seed creation or pre-flight fees
    assert len(stats_data["mandates"]) == 3
    assert len(stats_data["history"]) >= 4  # seed + dash_01 + dash_02 events


def test_dashboard_server_http(temp_db):
    """Verify the HTTP server serves the correct pages and API payloads."""
    # Seed some data
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("dash_http", 25.0)

    # Run the server in a separate background thread on a random available port
    DashboardHandler.db_path = temp_db
    server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    time.sleep(0.1)  # Allow server thread to start

    try:
        with httpx.Client() as client:
            # 1. Get HTML Page
            res_html = client.get(f"http://127.0.0.1:{port}/")
            assert res_html.status_code == 200
            assert "MINTRY.FABRIC" in res_html.text

            # 2. Get API Summary JSON
            res_api = client.get(f"http://127.0.0.1:{port}/api/summary")
            assert res_api.status_code == 200
            data = res_api.json()
            assert "stats" in data
            assert data["stats"]["total_mandates"] == 2  # seed + dash_http
            ids = [m["id"] for m in data["mandates"]]
            assert "dash_http" in ids
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_budget_allocation_flow(temp_db):
    """Verify that allocating and revoking budgets via dashboard endpoints works and propagates to SDK."""
    wallet = MintryWallet(db_path=temp_db)
    engine = PolicyEngine(wallet)

    DashboardHandler.db_path = temp_db
    server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    try:
        with httpx.Client() as client:
            # 1. Allocate budget via dashboard upsert
            payload_upsert = {
                "id": "dashboard_allocated_task",
                "budget_usd": 150.0,
                "expires_at": "2026-12-31T23:59:59Z"
            }
            res_upsert = client.post(f"http://127.0.0.1:{port}/api/mandates/upsert", json=payload_upsert)
            assert res_upsert.status_code == 200
            assert res_upsert.json()["success"] is True

            # Verify in SDK engine
            with engine.shield("dashboard_allocated_task") as mandate:
                assert mandate.id == "dashboard_allocated_task"
                assert mandate.max_usd == 150.0
                
                # Check pre-flight authorization works
                auth_ok = engine.authorize(mandate.id, None, deduct=False)
                assert auth_ok is True

            # 2. Revoke budget via dashboard revoke
            payload_revoke = {
                "id": "dashboard_allocated_task"
            }
            res_revoke = client.post(f"http://127.0.0.1:{port}/api/mandates/revoke", json=payload_revoke)
            assert res_revoke.status_code == 200
            assert res_revoke.json()["success"] is True

            # Assert authorization now fails instantly in SDK engine
            auth_revoked = engine.authorize("dashboard_allocated_task", None, deduct=False)
            assert auth_revoked is False
    finally:
        server.shutdown()
        server.server_close()

