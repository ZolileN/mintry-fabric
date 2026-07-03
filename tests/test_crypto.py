"""Tests for ES256 signature verification and policy bundle signing."""

import base64
import json
import pytest

from mintry.core.crypto import (
    verify_policy_bundle_signature,
    sign_policy_bundle,
    generate_policy_keypair,
)


def test_generate_keypair():
    """Test that we can generate a valid ES256 keypair."""
    private_pem, public_pem = generate_policy_keypair()
    assert "BEGIN PRIVATE KEY" in private_pem
    assert "BEGIN PUBLIC KEY" in public_pem


def test_sign_and_verify_policy_bundle():
    """Test signing and verifying a policy bundle."""
    private_pem, public_pem = generate_policy_keypair()

    bundle = {
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "control-plane",
    }

    # Sign the bundle
    signature = sign_policy_bundle(bundle, private_pem)
    assert signature
    assert isinstance(signature, str)

    # Add signature and verify
    bundle["signature"] = signature
    assert verify_policy_bundle_signature(bundle, public_pem) is True


def test_verify_rejects_invalid_signature():
    """Test that verification rejects an invalid signature."""
    private_pem, public_pem = generate_policy_keypair()

    bundle = {
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "signature": "invalid_signature_data",
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "control-plane",
    }

    assert verify_policy_bundle_signature(bundle, public_pem) is False


def test_verify_rejects_tampered_payload():
    """Test that verification fails if payload was tampered with."""
    private_pem, public_pem = generate_policy_keypair()

    bundle = {
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "control-plane",
    }

    # Sign the original
    signature = sign_policy_bundle(bundle, private_pem)

    # Tamper with the payload
    bundle["signature"] = signature
    bundle["mandates"]["agent_a"]["max_usd"] = 200.0

    # Should fail verification
    assert verify_policy_bundle_signature(bundle, public_pem) is False


def test_verify_requires_signature_field():
    """Test that verification fails if signature field is missing."""
    _, public_pem = generate_policy_keypair()

    bundle = {
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "issued_at": "2026-01-01T00:00:00Z",
    }

    assert verify_policy_bundle_signature(bundle, public_pem) is False


def test_different_keys_dont_verify():
    """Test that a signature from one keypair doesn't verify with another."""
    private_pem1, public_pem1 = generate_policy_keypair()
    private_pem2, public_pem2 = generate_policy_keypair()

    bundle = {
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "issued_at": "2026-01-01T00:00:00Z",
        "issued_by": "control-plane",
    }

    # Sign with key 1
    signature = sign_policy_bundle(bundle, private_pem1)
    bundle["signature"] = signature

    # Should not verify with key 2
    assert verify_policy_bundle_signature(bundle, public_pem2) is False

    # But should verify with key 1
    assert verify_policy_bundle_signature(bundle, public_pem1) is True
