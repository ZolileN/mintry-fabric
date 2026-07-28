"""P0 crypto contract + P1 enforce-loop integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mintry.core.crypto import (
    canonical_policy_payload_bytes,
    generate_policy_keypair,
    sign_policy_bundle,
    verify_policy_bundle_signature,
)
from mintry.core.engine import PolicyEngine
from mintry.core.policy_sync import PolicyBundle, PolicyCache
from mintry.core.wallet import MintryWallet


def test_canonical_payload_bytes_are_stable():
    bundle = {
        "version": 2,
        "mandates": {"agent_a": {"max_usd": 10.0}},
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "control-plane",
        "signature": "ignored",
    }
    expected = b'{"issued_at":"2026-01-01T00:00:00Z","issued_by":"control-plane","mandates":{"agent_a":{"max_usd":10.0}},"version":2}'
    assert canonical_policy_payload_bytes(bundle) == expected


def test_next_shaped_canonical_bytes_verify():
    """Simulate dashboard canonicalStringify field order then verify in Python."""
    private_pem, public_pem = generate_policy_keypair()
    payload = {
        "version": 1,
        "mandates": {"research_task": {"max_usd": 1.0}},
        "issued_at": "2026-07-28T00:00:00.000Z",
        "issued_by": "vercel_dashboard_signer",
    }
    # Dashboard builds object then JSON.stringify(sortKeysDeep(...))
    message = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert canonical_policy_payload_bytes(payload) == message

    signature = sign_policy_bundle(payload, private_pem)
    payload["signature"] = signature
    assert verify_policy_bundle_signature(payload, public_pem) is True


def test_disk_lkg_rejects_invalid_signature(tmp_path: Path):
    private_pem, public_pem = generate_policy_keypair()
    good = {
        "version": 1,
        "mandates": {"a": {"max_usd": 5.0}},
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "cp",
    }
    good["signature"] = sign_policy_bundle(good, private_pem)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "last_known_good.json").write_text(
        json.dumps(
            {
                "bundle": {**good, "signature": "bad"},
                "last_synced_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    def verify(bundle: PolicyBundle) -> bool:
        return verify_policy_bundle_signature(
            {
                "version": bundle.version,
                "mandates": bundle.mandates,
                "signature": bundle.signature,
                "issued_at": bundle.issued_at,
                "issued_by": bundle.issued_by,
            },
            public_pem,
        )

    cache = PolicyCache(cache_dir=cache_dir, verify_fn=verify)
    assert cache.get_active_policy() is None


def test_policy_cache_cap_blocks_interceptor(tmp_path: Path, monkeypatch):
    """Applied central policy must change allow/block on the hot path."""
    db = tmp_path / "ledger.db"
    wallet = MintryWallet(db_path=str(db))
    wallet.create_mandate("research_task", 100.0)  # local cap is high
    wallet.record_usage("research_task", 0.995)
    wallet.flush()

    engine = PolicyEngine(wallet)
    cache = PolicyCache(cache_dir=tmp_path / "pcache")
    bundle = PolicyBundle(
        version=3,
        mandates={"research_task": {"max_usd": 1.0}},
        signature="test",
        issued_at="2026-01-01T00:00:00Z",
        issued_by="test",
    )
    assert cache.apply_bundle(bundle, verify_fn=None) is True
    engine.policy_cache = cache

    # Hot path: no control-plane I/O — authorize uses local cache only
    assert engine.authorize("research_task", None, deduct=False) is False


def test_invalid_policy_keeps_lkg_enforcement(tmp_path: Path):
    wallet = MintryWallet(db_path=str(tmp_path / "w.db"))
    wallet.create_mandate("agent_a", 10.0)
    engine = PolicyEngine(wallet)
    cache = PolicyCache(cache_dir=tmp_path / "c")
    engine.policy_cache = cache

    good = PolicyBundle(
        version=1,
        mandates={"agent_a": {"max_usd": 10.0}},
        signature="ok",
        issued_at="2026-01-01T00:00:00Z",
        issued_by="cp",
    )
    assert cache.apply_bundle(good) is True

    bad = PolicyBundle(
        version=2,
        mandates={"agent_a": {"max_usd": 0.0}},
        signature="bad",
        issued_at="2026-01-02T00:00:00Z",
        issued_by="cp",
    )
    assert cache.apply_bundle(bad, verify_fn=lambda b: False) is False
    assert cache.get_active_policy().version == 1
    assert engine.authorize("agent_a", None, deduct=False) is True


def test_concurrent_reservations_respect_cap(tmp_path: Path):
    wallet = MintryWallet(db_path=str(tmp_path / "c.db"))
    wallet.create_mandate("m1", 0.02)
    engine = PolicyEngine(wallet)

    allowed = 0
    for _ in range(5):
        if engine.authorize("m1", None, deduct=False):
            allowed += 1
    # Each allow reserves $0.01 against $0.02 cap
    assert allowed == 2


def test_init_loads_public_key_from_env(tmp_path: Path, monkeypatch):
    import mintry

    _, public_pem = generate_policy_keypair()
    monkeypatch.setenv("MINTRY_API_KEY", "mk_test")
    monkeypatch.setenv("MINTRY_POLICY_PUBLIC_KEY", public_pem)
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("MINTRY_CONTROL_PLANE_KEY", raising=False)

    # Reset global engine between tests
    mintry._global_engine = None
    engine = mintry.init(db_path=str(tmp_path / "init.db"))
    assert engine.policy_sync_worker._verify_fn is not None
    mintry.close()
