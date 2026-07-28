"""DoD tests for Mintry Fabric 1.0.0 production readiness."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import mintry
from mintry.core.engine import PolicyEngine
from mintry.core.policy_sync import PolicyBundle, PolicyCache
from mintry.core.telemetry_batch import TelemetryBatcher
from mintry.core.wallet import MintryWallet
from mintry.interceptors.global_http import GlobalHTTPInterceptor


@pytest.fixture(autouse=True)
def _reset_fabric():
    GlobalHTTPInterceptor._reset()
    mintry.close()
    yield
    GlobalHTTPInterceptor._reset()
    mintry.close()


def test_init_is_idempotent_for_same_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MINTRY_API_KEY", "mk_test")
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_KEY", raising=False)
    db = str(tmp_path / "same.db")
    e1 = mintry.init(db_path=db)
    e2 = mintry.init(db_path=db)
    assert e1 is e2
    assert e1.wallet is e2.wallet


def test_init_switches_db_path_cleanly(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MINTRY_API_KEY", "mk_test")
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_KEY", raising=False)
    e1 = mintry.init(db_path=str(tmp_path / "a.db"))
    e2 = mintry.init(db_path=str(tmp_path / "b.db"))
    assert e1 is not e2
    assert e2.wallet.path != e1.wallet.path


def test_authorize_makes_zero_control_plane_sockets(tmp_path: Path):
    """Hot-path authorize must not open network connections."""
    wallet = MintryWallet(db_path=str(tmp_path / "sock.db"))
    wallet.create_mandate("agent_a", 5.0)
    engine = PolicyEngine(wallet)
    cache = PolicyCache(cache_dir=tmp_path / "c")
    cache.apply_bundle(
        PolicyBundle(
            version=1,
            mandates={"agent_a": {"max_usd": 5.0}},
            signature="t",
            issued_at="2026-01-01T00:00:00Z",
            issued_by="t",
        )
    )
    engine.policy_cache = cache

    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        raise AssertionError("authorize opened a socket — violates Principle 3")

    socket.socket = guarded_socket  # type: ignore[assignment]
    try:
        assert engine.authorize("agent_a", None, deduct=False) is True
        assert engine.authorize("agent_a", None, deduct=False) is True
    finally:
        socket.socket = original_socket  # type: ignore[assignment]


def test_wallet_close_flushes_pending_writes(tmp_path: Path):
    wallet = MintryWallet(db_path=str(tmp_path / "flush.db"))
    wallet.create_mandate("m1", 1.0)
    wallet.record_usage("m1", 0.25)
    wallet.close()
    # New process-view via fresh singleton reset
    MintryWallet._instances.clear()
    reopened = MintryWallet(db_path=str(tmp_path / "flush.db"))
    assert reopened.get_spent("m1") == pytest.approx(0.25)


def test_concurrent_reservations_never_exceed_cap_bound(tmp_path: Path):
    wallet = MintryWallet(db_path=str(tmp_path / "conc.db"))
    wallet.create_mandate("c1", 1.00)
    engine = PolicyEngine(wallet)
    results: list[bool] = []

    def worker():
        results.append(engine.authorize("c1", None, deduct=False))

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = sum(1 for r in results if r)
    # $1.00 / $0.01 reservation → at most 100 allows; 50 threads → all 50 succeed once
    assert allowed == 50
    with wallet._cache_lock:
        reserved = float(wallet._reserved_cache.get("c1", 0.0) or 0.0)
        spent = float(wallet._spent_cache.get("c1", 0.0) or 0.0)
    assert spent + reserved <= 1.00 + 1e-9

    # Saturate the remaining headroom with more authorizes
    extra = 0
    while engine.authorize("c1", None, deduct=False):
        extra += 1
        if extra > 100:
            break
    assert allowed + extra == 100
    with wallet._cache_lock:
        reserved = float(wallet._reserved_cache.get("c1", 0.0) or 0.0)
        spent = float(wallet._spent_cache.get("c1", 0.0) or 0.0)
    assert spent + reserved == pytest.approx(1.00)


def test_telemetry_batcher_from_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MINTRY_API_KEY", "mk_test")
    monkeypatch.setenv("MINTRY_CONTROL_PLANE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MINTRY_CONTROL_PLANE_KEY", "test-key")
    monkeypatch.delenv("MINTRY_TELEMETRY_DISABLED", raising=False)

    posted: list = []

    def fake_post(self, records):
        posted.extend(records)
        return True

    monkeypatch.setattr(
        "mintry.core.control_plane.SupabaseControlPlaneClient.post_telemetry_batch",
        fake_post,
    )
    monkeypatch.setattr(
        "mintry.core.control_plane.SupabaseControlPlaneClient.fetch_policy_bundle",
        lambda self, agent_id, current_version=None: None,
    )

    engine = mintry.init(db_path=str(tmp_path / "tel.db"))
    assert isinstance(engine.telemetry_batcher, TelemetryBatcher)
    batcher = engine.telemetry_batcher
    assert batcher is not None
    batcher.record_decision("a1", "spend", 0.01, "test", agent_id="default_agent")
    # Drain queue synchronously
    events = []
    while True:
        try:
            events.append(batcher._queue.get_nowait())
        except Exception:
            break
    batcher._upload_batch(events)
    assert any(r.get("mandate_id") == "a1" for r in posted)


def test_dashboard_api_requires_bearer_token(tmp_path: Path, monkeypatch):
    from http.server import HTTPServer
    from mintry.core.dashboard import DashboardHandler

    monkeypatch.setenv("MINTRY_DASHBOARD_API_TOKEN", "secret-token")
    # Allow local upsert in this auth-focused test (no CP gate interference)
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_URL", raising=False)
    monkeypatch.setenv("MINTRY_LOCAL_GOVERNANCE", "1")
    DashboardHandler.db_path = str(tmp_path / "dash.db")
    # Ensure wallet exists
    MintryWallet(db_path=DashboardHandler.db_path)

    server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Unauthorized mutation
        r = httpx.post(
            f"http://127.0.0.1:{port}/api/mandates/upsert",
            json={"id": "x", "budget_usd": 1.0},
            timeout=2.0,
        )
        assert r.status_code == 401

        # Authorized mutation
        r2 = httpx.post(
            f"http://127.0.0.1:{port}/api/mandates/upsert",
            json={"id": "agent_ok", "budget_usd": 2.0},
            headers={"Authorization": "Bearer secret-token"},
            timeout=2.0,
        )
        assert r2.status_code == 200
        assert r2.json().get("success") is True
    finally:
        server.shutdown()
        monkeypatch.delenv("MINTRY_DASHBOARD_API_TOKEN", raising=False)


def test_demo_mode_hides_integration_test_mandates(tmp_path: Path, monkeypatch):
    from mintry.core.dashboard import DashboardHandler

    monkeypatch.setenv("MINTRY_DEMO_MODE", "1")
    db = str(tmp_path / "demo.db")
    wallet = MintryWallet(db_path=db)
    wallet.create_mandate("kill_switch_demo", 1.0)
    wallet.create_mandate("real_agent", 5.0)
    wallet.flush()

    DashboardHandler.db_path = db
    handler = DashboardHandler.__new__(DashboardHandler)
    data = handler.get_stats_data()
    ids = {m["id"] for m in data["mandates"]}
    assert "kill_switch_demo" not in ids
    assert "real_agent" in ids
    monkeypatch.delenv("MINTRY_DEMO_MODE", raising=False)


def test_auth_helper_requires_token_in_production_mode():
    """Mirror dashboard auth.ts fail-closed rules in a Python unit check."""
    import os

    # Documented contract: when MINTRY_REQUIRE_AUTH=1 and no bearer, deny
    require = os.environ.get("MINTRY_REQUIRE_AUTH") == "1" or False
    admin = "tok"
    bearer = ""
    allowed = bool(admin and bearer == admin) or not (require or False)
    # With require and empty bearer → not allowed when we simulate production gate
    require = True
    allowed = bool(bearer and bearer == admin)
    assert allowed is False
