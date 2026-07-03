"""Tests for Supabase control plane client."""

import json
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock
import urllib.error

from mintry.core.control_plane import SupabaseControlPlaneClient


def _mock_urlopen(status: int, body: bytes):
    """Helper: create a mock urllib response."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_client_initialization():
    """Test control plane client initialization."""
    client = SupabaseControlPlaneClient(
        control_plane_url="https://project.supabase.co",
        api_key="test_key",
    )
    assert client.url == "https://project.supabase.co"
    assert client.api_key == "test_key"


def test_client_falls_back_to_env_vars():
    """Test that client reads from environment variables if not provided."""
    with patch.dict('os.environ', {
        'MINTRY_CONTROL_PLANE_URL': 'https://env-url.supabase.co',
        'MINTRY_CONTROL_PLANE_KEY': 'env_key',
    }):
        client = SupabaseControlPlaneClient()
        assert client.url == 'https://env-url.supabase.co'
        assert client.api_key == 'env_key'


def test_client_warns_when_not_configured():
    """Test that client warns when not configured."""
    with patch('mintry.core.control_plane.logger') as mock_logger:
        client = SupabaseControlPlaneClient()
        assert not client.url
        mock_logger.warning.assert_called()


def test_fetch_policy_bundle_success():
    """Test successful policy bundle fetch."""
    bundle_data = [{
        "version": 1,
        "mandates": {"agent_a": {"max_usd": 100.0}},
        "signature": "sig_v1",
        "issued_at": "2026-01-01T00:00:00Z",
    }]
    mock_resp = _mock_urlopen(200, json.dumps(bundle_data).encode())

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        result = client.fetch_policy_bundle("agent_1")

    assert result is not None
    assert result["version"] == 1


def test_fetch_policy_bundle_no_update():
    """Test fetch when no policy update available."""
    mock_resp = _mock_urlopen(200, b"[]")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        result = client.fetch_policy_bundle("agent_1")

    assert result is None


def test_fetch_policy_bundle_http_error():
    """Test fetch when HTTP error occurs."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection failed")):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        result = client.fetch_policy_bundle("agent_1")

    assert result is None


def test_post_telemetry_batch_success():
    """Test successful telemetry batch upload."""
    mock_resp = _mock_urlopen(201, b"")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        records = [
            {"timestamp": "2026-01-01T00:00:00Z", "action": "allow", "amount": 0.01},
        ]
        result = client.post_telemetry_batch(records)

    assert result is True


def test_post_telemetry_batch_http_error():
    """Test telemetry POST when error occurs."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection failed")):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        records = [{"timestamp": "2026-01-01T00:00:00Z", "action": "allow"}]
        result = client.post_telemetry_batch(records)

    assert result is False


def test_post_telemetry_batch_empty():
    """Test that empty batch is skipped."""
    client = SupabaseControlPlaneClient(
        control_plane_url="https://test.supabase.co",
        api_key="test_key",
    )
    result = client.post_telemetry_batch([])
    assert result is True  # Empty batch is no-op


def test_health_check_success():
    """Test successful health check."""
    mock_resp = _mock_urlopen(200, b"[]")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        result = client.health_check()

    assert result is True


def test_health_check_failure():
    """Test failed health check."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection failed")):
        client = SupabaseControlPlaneClient(
            control_plane_url="https://test.supabase.co",
            api_key="test_key",
        )
        result = client.health_check()

    assert result is False
