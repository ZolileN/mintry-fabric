"""Tests for governance mode (central Sign & Push vs local ledger)."""

from __future__ import annotations

import threading
from http.server import HTTPServer
from pathlib import Path

import httpx

from mintry.core.dashboard import DashboardHandler
from mintry.core.governance import local_governance_enabled
from mintry.core.wallet import MintryWallet


def test_local_governance_when_no_control_plane(monkeypatch):
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("MINTRY_LOCAL_GOVERNANCE", raising=False)
    monkeypatch.delenv("MINTRY_REQUIRE_LOCAL_GOVERNANCE_FLAG", raising=False)
    assert local_governance_enabled() is True


def test_local_governance_gated_when_control_plane_set(monkeypatch):
    monkeypatch.setenv("MINTRY_CONTROL_PLANE_URL", "https://example.supabase.co")
    monkeypatch.delenv("MINTRY_LOCAL_GOVERNANCE", raising=False)
    monkeypatch.delenv("MINTRY_REQUIRE_LOCAL_GOVERNANCE_FLAG", raising=False)
    assert local_governance_enabled() is False


def test_local_governance_opt_in_with_control_plane(monkeypatch):
    monkeypatch.setenv("MINTRY_CONTROL_PLANE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MINTRY_LOCAL_GOVERNANCE", "1")
    assert local_governance_enabled() is True


def test_dashboard_blocks_local_upsert_when_cp_configured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MINTRY_CONTROL_PLANE_URL", "https://example.supabase.co")
    monkeypatch.delenv("MINTRY_LOCAL_GOVERNANCE", raising=False)
    monkeypatch.delenv("MINTRY_DASHBOARD_API_TOKEN", raising=False)

    DashboardHandler.db_path = str(tmp_path / "gov.db")
    MintryWallet(db_path=DashboardHandler.db_path)

    server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{port}/api/mandates/upsert",
            json={"id": "x", "budget_usd": 1.0},
            timeout=2.0,
        )
        assert r.status_code == 403
        assert "Sign & Push" in r.json()["error"]

        summary = httpx.get(f"http://127.0.0.1:{port}/api/summary", timeout=2.0)
        assert summary.status_code == 200
        gov = summary.json()["governance"]
        assert gov["control_plane_configured"] is True
        assert gov["local_governance"] is False
        assert gov["authoring_mode"] == "central_sign_and_push"
    finally:
        server.shutdown()
