"""Tests for OPA bundle evaluation."""

import json
import pytest
import tempfile
from pathlib import Path

from mintry.core.opa import OPABundleEvaluator


def test_opa_evaluator_initialization():
    """Test OPA evaluator initialization."""
    evaluator = OPABundleEvaluator()
    assert evaluator.bundle_path is not None


def test_opa_evaluator_with_custom_path():
    """Test OPA evaluator with custom bundle path."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        assert evaluator.bundle_path == bundle_path


def test_load_bundle_missing_file():
    """Test loading bundle when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "nonexistent.json"
        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        assert evaluator.load_bundle() is False


def test_load_bundle_success():
    """Test successful bundle loading."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "metadata": {"version": "1.0"},
            "data": {"mintry": {"policies": ["allow", "block"]}},
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        assert evaluator.load_bundle() is True


def test_load_bundle_invalid_json():
    """Test loading bundle with invalid JSON."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_path.write_text("{ invalid json }")

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        assert evaluator.load_bundle() is False


def test_validate_bundle_success():
    """Test bundle validation with valid bundle."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "metadata": {"version": "1.0"},
            "data": {"mintry": {"policies": []}},
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        evaluator.load_bundle()
        assert evaluator.validate_bundle() is True


def test_validate_bundle_missing_metadata():
    """Test bundle validation with missing metadata."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "data": {"mintry": {}},
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        evaluator.load_bundle()
        assert evaluator.validate_bundle() is False


def test_evaluate_in_process_simple_query():
    """Test in-process evaluation of simple query."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "metadata": {"version": "1.0"},
            "data": {
                "mintry": {
                    "mandate": {
                        "agent_1": {"max_usd": 100.0},
                    }
                }
            },
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        evaluator.load_bundle()

        result = evaluator._evaluate_in_process("data.mintry.mandate", {})
        assert result is not None
        assert "agent_1" in result


def test_evaluate_in_process_nested_query():
    """Test in-process evaluation of nested query."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "metadata": {"version": "1.0"},
            "data": {
                "mintry": {
                    "mandate": {
                        "agent_1": {"max_usd": 100.0},
                    }
                }
            },
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        evaluator.load_bundle()

        result = evaluator._evaluate_in_process("data.mintry.mandate.agent_1", {})
        assert result is not None
        assert result["max_usd"] == 100.0


def test_evaluate_without_loaded_bundle():
    """Test evaluate without a loaded bundle."""
    evaluator = OPABundleEvaluator()
    result = evaluator.evaluate("data.test.query", {})
    assert result is None


def test_evaluate_with_invalid_query():
    """Test evaluate with query that doesn't start with 'data.'"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.json"
        bundle_data = {
            "metadata": {"version": "1.0"},
            "data": {"test": {}},
        }
        bundle_path.write_text(json.dumps(bundle_data))

        evaluator = OPABundleEvaluator(bundle_path=bundle_path)
        evaluator.load_bundle()

        result = evaluator._evaluate_in_process("invalid.query", {})
        assert result is None
