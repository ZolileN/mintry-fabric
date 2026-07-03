"""Tests for policy cache and sync worker."""

import json
import sqlite3
from pathlib import Path

from mintry.core.policy_sync import PolicyBundle, PolicyCache, PolicySyncWorker
from mintry.core.wallet import MintryWallet


def test_policy_cache_atomic_swap(tmp_path):
    cache = PolicyCache(cache_dir=tmp_path)
    bundle_v1 = PolicyBundle(
        version=1,
        mandates={"agent_a": {"max_usd": 50.0}},
        signature="sig_v1",
        issued_at="2026-01-01T00:00:00Z",
    )
    assert cache.apply_bundle(bundle_v1) is True
    assert cache.get_active_policy().version == 1

    bundle_v0 = PolicyBundle(
        version=0,
        mandates={},
        signature="sig_v0",
        issued_at="2026-01-01T00:00:00Z",
    )
    assert cache.apply_bundle(bundle_v0) is False
    assert cache.get_active_policy().version == 1


def test_policy_cache_rejects_invalid_signature(tmp_path):
    cache = PolicyCache(cache_dir=tmp_path)
    bundle = PolicyBundle(
        version=1,
        mandates={"agent_a": {"max_usd": 10.0}},
        signature="bad",
        issued_at="2026-01-01T00:00:00Z",
    )
    assert cache.apply_bundle(bundle, verify_fn=lambda b: b.signature == "good") is False
    assert cache.get_active_policy() is None
    assert cache.get_sync_status()["last_sync_error"] == "signature_verification_failed"


def test_policy_cache_persists_to_disk(tmp_path):
    cache = PolicyCache(cache_dir=tmp_path)
    bundle = PolicyBundle(
        version=3,
        mandates={"research_agent": {"max_usd": 250.0}},
        signature="sig_v3",
        issued_at="2026-01-01T00:00:00Z",
    )
    cache.apply_bundle(bundle)

    reloaded = PolicyCache(cache_dir=tmp_path)
    active = reloaded.get_active_policy()
    assert active.version == 3
    assert active.mandates["research_agent"]["max_usd"] == 250.0


def test_policy_sync_worker_poll_once(tmp_path):
    cache = PolicyCache(cache_dir=tmp_path)
    payloads = [
        {
            "version": 1,
            "mandates": {"a": {"max_usd": 5.0}},
            "signature": "ok",
            "issued_at": "2026-01-01T00:00:00Z",
        }
    ]

    worker = PolicySyncWorker(cache, fetch_fn=lambda: payloads.pop(0) if payloads else None)
    assert worker.poll_once() is True
    assert cache.get_active_policy().version == 1

    assert worker.poll_once() is False


def test_policy_cache_persists_to_wallet(tmp_path):
    """Test that policy versions are persisted to wallet database."""
    db_path = tmp_path / "test.db"
    wallet = MintryWallet(db_path=str(db_path))
    cache = PolicyCache(cache_dir=tmp_path, wallet=wallet)

    bundle = PolicyBundle(
        version=1,
        mandates={"agent_a": {"max_usd": 100.0}},
        signature="sig_v1",
        issued_at="2026-01-01T00:00:00Z",
        issued_by="control-plane",
    )

    assert cache.apply_bundle(bundle) is True

    # Verify it was persisted to wallet
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT version, signature FROM policy_versions WHERE version = 1")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 1
    assert row[1] == "sig_v1"


def test_get_policy_history(tmp_path):
    """Test retrieving policy version history."""
    db_path = tmp_path / "test.db"
    wallet = MintryWallet(db_path=str(db_path))
    cache = PolicyCache(cache_dir=tmp_path, wallet=wallet)

    # Apply multiple versions
    for v in range(1, 4):
        bundle = PolicyBundle(
            version=v,
            mandates={"agent": {"max_usd": float(v * 100)}},
            signature=f"sig_v{v}",
            issued_at="2026-01-01T00:00:00Z",
            issued_by="control-plane",
        )
        cache.apply_bundle(bundle)

    # Get history
    history = cache.get_policy_history(limit=10)

    # Should have 3 versions (most recent first)
    assert len(history) == 3
    assert history[0]["version"] == 3  # Most recent
    assert history[2]["version"] == 1  # Oldest


def test_get_policy_history_limit(tmp_path):
    """Test that policy history respects limit."""
    db_path = tmp_path / "test.db"
    wallet = MintryWallet(db_path=str(db_path))
    cache = PolicyCache(cache_dir=tmp_path, wallet=wallet)

    # Apply 5 versions
    for v in range(1, 6):
        bundle = PolicyBundle(
            version=v,
            mandates={"agent": {"max_usd": float(v * 100)}},
            signature=f"sig_v{v}",
            issued_at="2026-01-01T00:00:00Z",
        )
        cache.apply_bundle(bundle)

    # Get history with limit
    history = cache.get_policy_history(limit=2)

    assert len(history) == 2
    assert history[0]["version"] == 5  # Most recent


def test_rollback_to_version(tmp_path):
    """Test rolling back to a previous policy version."""
    db_path = tmp_path / "test.db"
    wallet = MintryWallet(db_path=str(db_path))
    cache = PolicyCache(cache_dir=tmp_path, wallet=wallet)

    # Apply versions 1, 2, 3
    for v in range(1, 4):
        bundle = PolicyBundle(
            version=v,
            mandates={"agent": {"max_usd": float(v * 100)}},
            signature=f"sig_v{v}",
            issued_at="2026-01-01T00:00:00Z",
        )
        cache.apply_bundle(bundle)

    # Verify we're at v3
    assert cache.get_active_policy().version == 3

    # Rollback to v1
    success = cache.rollback_to_version(1)
    assert success is True

    # Verify we're back to v1
    active = cache.get_active_policy()
    assert active.version == 1
    assert active.mandates["agent"]["max_usd"] == 100.0


def test_rollback_to_nonexistent_version(tmp_path):
    """Test rollback to a version that doesn't exist."""
    db_path = tmp_path / "test.db"
    wallet = MintryWallet(db_path=str(db_path))
    cache = PolicyCache(cache_dir=tmp_path, wallet=wallet)

    bundle = PolicyBundle(
        version=1,
        mandates={"agent": {"max_usd": 100.0}},
        signature="sig_v1",
        issued_at="2026-01-01T00:00:00Z",
    )
    cache.apply_bundle(bundle)

    # Try to rollback to nonexistent version
    success = cache.rollback_to_version(999)
    assert success is False

    # Should still be at v1
    assert cache.get_active_policy().version == 1
