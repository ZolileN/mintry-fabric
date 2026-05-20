"""Tests for Sprint 3: Async support, per-model pricing, mandate expiry, and signature verification."""

import pytest
import asyncio
import httpx
import json
import mintry
from datetime import datetime, timezone, timedelta
from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.pricing import calculate_cost, get_model_rates, register_model, list_models
from mintry.models.mandates import AP2IntentMandate, sign_mandate
from cryptography.hazmat.primitives.asymmetric import ec


@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and use a fresh temp database for every test."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


# ── Task 12: Async Interception ─────────────────────────────────────


@pytest.mark.anyio
async def test_async_interception_metering(tmp_path, httpx_mock):
    """Async httpx.AsyncClient requests are intercepted and metered."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    mandate_id = "mt_task_882x"
    fabric.wallet.add_funds(mandate_id, 1.00)

    mock_response = {
        "id": "chatcmpl-async",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 500, "completion_tokens": 500, "total_tokens": 1000},
        "choices": [{"message": {"role": "assistant", "content": "Async metered."}}]
    }

    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json=mock_response,
        status_code=200
    )

    initial_spent = fabric.wallet.get_spent(mandate_id)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
            headers={"x-mintry-mandate": mandate_id}
        )

    final_spent = fabric.wallet.get_spent(mandate_id)
    delta = final_spent - initial_spent

    # gpt-4o: 500 * 0.0000025 + 500 * 0.00001 = 0.00125 + 0.005 = 0.00625
    assert delta == pytest.approx(0.00625, rel=1e-3)
    print(f"\n[SUCCESS] Async metering: delta=${delta:.6f}")


@pytest.mark.anyio
async def test_async_budget_enforcement(tmp_path):
    """Async requests are blocked when mandate budget is exhausted."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    # Create a mandate with no budget
    fabric.wallet.create_mandate("broke_async", 0.005)
    fabric.wallet.record_usage("broke_async", 0.005)

    async with httpx.AsyncClient() as client:
        with pytest.raises(PermissionError, match="Budget Exhausted"):
            await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                headers={"x-mintry-mandate": "broke_async"}
            )

    print("\n[SUCCESS] Async budget enforcement works.")


@pytest.mark.anyio
async def test_async_intent_blocking(tmp_path):
    """Async requests with prohibited intent are blocked."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    fabric.wallet.add_funds("mt_task_882x", 1.00)

    async with httpx.AsyncClient() as client:
        with pytest.raises(PermissionError, match="Prohibited Intent"):
            await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "delete vouchers.db now"}]},
                headers={"x-mintry-mandate": "mt_task_882x"}
            )

    print("\n[SUCCESS] Async intent blocking works.")


# ── Task 13: Per-Model Pricing ──────────────────────────────────────


def test_per_model_pricing_openai():
    """OpenAI models use differentiated input/output pricing."""
    # GPT-5: $5/$15 per million tokens
    cost = calculate_cost("gpt-5-preview", prompt_tokens=1000, completion_tokens=1000)
    expected = (1000 * 0.000005) + (1000 * 0.000015)  # $0.005 + $0.015 = $0.020
    assert cost == pytest.approx(expected, rel=1e-5)
    print(f"\n[SUCCESS] GPT-5 pricing: ${cost:.6f}")


def test_per_model_pricing_anthropic():
    """Anthropic Claude models use their own pricing."""
    cost = calculate_cost("claude-sonnet-4-20250514", prompt_tokens=1000, completion_tokens=500)
    expected = (1000 * 0.000003) + (500 * 0.000015)  # $0.003 + $0.0075 = $0.0105
    assert cost == pytest.approx(expected, rel=1e-5)
    print(f"\n[SUCCESS] Claude Sonnet 4 pricing: ${cost:.6f}")


def test_per_model_pricing_gemini():
    """Google Gemini models use their own pricing."""
    cost = calculate_cost("gemini-2.5-flash", prompt_tokens=2000, completion_tokens=1000)
    expected = (2000 * 0.00000015) + (1000 * 0.0000006)  # $0.0003 + $0.0006 = $0.0009
    assert cost == pytest.approx(expected, rel=1e-5)
    print(f"\n[SUCCESS] Gemini 2.5 Flash pricing: ${cost:.6f}")


def test_per_model_pricing_fallback():
    """Unknown models fall back to the default rate."""
    cost = calculate_cost("unknown-model-xyz", prompt_tokens=1000, completion_tokens=1000)
    expected = (1000 * 0.000005) + (1000 * 0.000005)  # Fallback: $0.005 + $0.005 = $0.01
    assert cost == pytest.approx(expected, rel=1e-5)
    print(f"\n[SUCCESS] Fallback pricing: ${cost:.6f}")


def test_custom_model_registration():
    """Teams can register custom pricing for fine-tuned models."""
    register_model("ft:gpt-4o-custom", input_rate=0.00001, output_rate=0.00003)
    rates = get_model_rates("ft:gpt-4o-custom")
    assert rates["input"] == 0.00001
    assert rates["output"] == 0.00003
    assert "ft:gpt-4o-custom" in list_models()
    print("\n[SUCCESS] Custom model registered successfully.")


def test_pricing_integrated_with_interceptor(tmp_path, httpx_mock):
    """The interceptor uses per-model pricing for post-flight metering."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)
    fabric.wallet.create_mandate("pricing_test", 1.00)

    # Mock a GPT-5-preview response
    httpx_mock.add_response(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        json={
            "id": "chatcmpl-pricing",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-5-preview",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
            "choices": [{"message": {"role": "assistant", "content": "priced."}}]
        },
        status_code=200
    )

    from openai import OpenAI
    client = OpenAI(api_key="sk-mock-key")
    client.chat.completions.create(
        model="gpt-5-preview",
        messages=[{"role": "user", "content": "test"}],
        extra_headers={"X-Mintry-Mandate": "pricing_test"}
    )

    spent = fabric.wallet.get_spent("pricing_test")
    # GPT-5: 1000 * $0.000005 + 1000 * $0.000015 = $0.020
    assert spent == pytest.approx(0.020, rel=1e-3)
    print(f"\n[SUCCESS] Interceptor used per-model pricing: ${spent:.6f}")


# ── Task 14: Mandate Expiry ─────────────────────────────────────────


def test_expired_mandate_rejected(tmp_path):
    """Expired mandates are rejected at authorization time."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    # Create a mandate that expired 1 hour ago
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    fabric.wallet.create_mandate("expired_mandate", max_usd=10.0, expires_at=past)

    assert fabric.wallet.is_expired("expired_mandate") is True

    # Authorization should fail
    import httpx as hx
    mock_request = hx.Request("POST", "https://api.openai.com/v1/chat/completions")
    assert fabric.authorize("expired_mandate", mock_request) is False
    print("\n[SUCCESS] Expired mandate rejected.")


def test_active_mandate_not_expired(tmp_path):
    """Mandates with future expiry are accepted."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    # Create a mandate that expires in 1 hour
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    fabric.wallet.create_mandate("future_mandate", max_usd=10.0, expires_at=future)

    assert fabric.wallet.is_expired("future_mandate") is False

    import httpx as hx
    mock_request = hx.Request("POST", "https://api.openai.com/v1/chat/completions")
    assert fabric.authorize("future_mandate", mock_request) is True
    print("\n[SUCCESS] Active mandate accepted.")


def test_mandate_without_expiry_never_expires(tmp_path):
    """Mandates without an expires_at are always valid."""
    db = str(tmp_path / "vouchers.db")
    fabric = mintry.init(api_key="test_key_2026", db_path=db)

    fabric.wallet.create_mandate("no_expiry", max_usd=10.0)
    assert fabric.wallet.is_expired("no_expiry") is False
    print("\n[SUCCESS] Mandate without expiry never expires.")


# ── Task 15: AP2IntentMandate Signature Verification ────────────────


def test_valid_signature_verification():
    """A correctly signed mandate passes verification."""
    # Generate a fresh ES256 key pair
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    mandate = AP2IntentMandate(
        mandate_id="mt_signed_001",
        user_id="agent_alpha",
        max_budget=5.00,
        currency="USD",
        resource_scope=["inference"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        signature="placeholder",
    )

    # Sign the mandate
    mandate.signature = sign_mandate(mandate, private_key)

    # Verify
    assert mandate.verify_signature(public_key) is True
    print(f"\n[SUCCESS] Valid signature verified: {mandate.signature[:32]}...")


def test_invalid_signature_rejected():
    """A mandate with a tampered signature fails verification."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    mandate = AP2IntentMandate(
        mandate_id="mt_signed_002",
        user_id="agent_beta",
        max_budget=10.00,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        signature="placeholder",
    )

    # Sign it, then tamper
    mandate.signature = sign_mandate(mandate, private_key)
    mandate.max_budget = 99999.00  # Tamper the budget

    # Verification should fail
    assert mandate.verify_signature(public_key) is False
    print("\n[SUCCESS] Tampered signature correctly rejected.")


def test_wrong_key_rejected():
    """A mandate verified against the wrong public key fails."""
    key1 = ec.generate_private_key(ec.SECP256R1())
    key2 = ec.generate_private_key(ec.SECP256R1())

    mandate = AP2IntentMandate(
        mandate_id="mt_signed_003",
        user_id="agent_gamma",
        max_budget=1.00,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        signature="placeholder",
    )

    mandate.signature = sign_mandate(mandate, key1)

    # Verify with wrong key
    assert mandate.verify_signature(key2.public_key()) is False
    print("\n[SUCCESS] Wrong key correctly rejected.")


def test_malformed_signature_raises():
    """A mandate with an invalid base64 signature raises ValueError."""
    public_key = ec.generate_private_key(ec.SECP256R1()).public_key()

    mandate = AP2IntentMandate(
        mandate_id="mt_bad_sig",
        user_id="agent_delta",
        max_budget=1.00,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        signature="not-valid-base64!!!",
    )

    with pytest.raises(ValueError, match="Malformed signature"):
        mandate.verify_signature(public_key)

    print("\n[SUCCESS] Malformed signature raises ValueError.")


def test_expired_mandate_model():
    """AP2IntentMandate.is_expired() correctly detects expiry."""
    expired = AP2IntentMandate(
        mandate_id="mt_exp",
        user_id="agent",
        max_budget=1.00,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        signature="placeholder",
    )
    assert expired.is_expired() is True

    active = AP2IntentMandate(
        mandate_id="mt_act",
        user_id="agent",
        max_budget=1.00,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        signature="placeholder",
    )
    assert active.is_expired() is False
    print("\n[SUCCESS] AP2IntentMandate.is_expired() works correctly.")
