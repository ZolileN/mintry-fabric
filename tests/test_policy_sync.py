"""Tests for policy cache and sync worker."""

import json
from pathlib import Path

from mintry.core.policy_sync import PolicyBundle, PolicyCache, PolicySyncWorker


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
