"""Tests for OPA sync-time materialization (Phase 2 E4)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mintry.core.opa import OPABundleEvaluator, materialize_flat_rules


def test_materialize_flat_mandates():
    rules = materialize_flat_rules(
        {"agent_1": {"max_usd": 50, "allow": True, "expires_at": "2026-01-01T00:00:00Z"}}
    )
    assert rules["agent_1"]["max_usd"] == 50.0
    assert rules["agent_1"]["allow"] is True


def test_materialize_opa_shaped_envelope():
    rules = materialize_flat_rules(
        {"mandate": {"agent_1": {"max_usd": 10, "allow": False}}}
    )
    assert rules["agent_1"]["allow"] is False
    assert rules["agent_1"]["max_usd"] == 10.0


def test_set_bundle_materializes_flat_rules():
    ev = OPABundleEvaluator()
    flat = ev.set_bundle_data({"agent_x": {"max_usd": 99.0}})
    assert flat["agent_x"]["max_usd"] == 99.0
    result = ev.evaluate("data.mintry.mandate.agent_x", {})
    assert result["max_usd"] == 99.0


def test_evaluate_allow_false():
    ev = OPABundleEvaluator()
    ev.set_bundle_data({"agent_x": {"max_usd": 10.0, "allow": False}})
    assert ev.evaluate("data.mintry.mandate.agent_x", {}) is False


def test_evaluate_never_requires_cli(tmp_path: Path):
    """Even with a bundle on disk, evaluate uses in-process materialization only."""
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0"},
                "data": {"mintry": {"mandate": {"a1": {"max_usd": 5.0}}}},
            }
        )
    )
    ev = OPABundleEvaluator(bundle_path=bundle_path)
    assert ev.load_bundle() is True
    assert ev.flat_rules["a1"]["max_usd"] == 5.0
    assert ev.evaluate("data.mintry.mandate.a1", {"cost": 0.01})["max_usd"] == 5.0
