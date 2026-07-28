"""Tests for Vault alias-only secret resolution."""

from __future__ import annotations

import pytest

from mintry.core.secrets import (
    SecretRef,
    SecretResolutionError,
    resolve_provider_key,
    resolve_secret,
    validate_alias,
)


def test_validate_alias_ok():
    assert validate_alias("OPENAI_PROD_KEY") is None


def test_validate_alias_rejects_raw_key_shape():
    assert validate_alias("sk-abc123") is not None


def test_resolve_secret_from_environ():
    value = resolve_secret("OPENAI_PROD_KEY", environ={"OPENAI_PROD_KEY": "secret-value"})
    assert value == "secret-value"


def test_resolve_secret_missing():
    with pytest.raises(SecretResolutionError):
        resolve_secret("OPENAI_PROD_KEY", environ={})


def test_resolve_provider_key_conventional():
    key = resolve_provider_key(
        "openai",
        environ={"OPENAI_API_KEY": "sk-test"},
    )
    assert key == "sk-test"


def test_resolve_provider_key_via_alias_map():
    key = resolve_provider_key(
        "openai",
        aliases={"openai": "OPENAI_PROD_KEY"},
        environ={"OPENAI_PROD_KEY": "from-alias"},
    )
    assert key == "from-alias"


def test_secret_ref_roundtrip():
    ref = SecretRef(alias="ANTHROPIC_PROD_KEY", provider="anthropic", description="prod")
    assert SecretRef.from_dict(ref.to_dict()).alias == "ANTHROPIC_PROD_KEY"
