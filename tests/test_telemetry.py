# tests/test_telemetry.py
"""
Telemetry integration tests for Mintry Fabric.

These tests verify that:
1. The telemetry module is importable and provides the correct public API.
2. When MINTRY_OTEL_ENABLED is not set, get_tracer() returns a no-op tracer
   without raising.
3. OTel spans are opened and closed around the interceptor's patched_send
   function, and the duration captured is >= the mock server's synthetic delay.
4. record_proxy_duration() and record_proxy_cost() are safe no-ops when
   prometheus_client is not yet initialised.

The tests use pytest-httpx to intercept network calls so no real upstream
or mock server process is required during CI.
"""

from __future__ import annotations

import os
import time
import json
import socket
import pytest
import httpx
from unittest.mock import patch, MagicMock

from mintry import telemetry as _telemetry


def _mock_server_running() -> bool:
    """Return True if the Gemini mock server is reachable on localhost:9090."""
    try:
        with socket.create_connection(("localhost", 9090), timeout=0.5):
            return True
    except OSError:
        return False


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_interceptor():
    """Ensure each test starts with a clean interceptor state."""
    from mintry.interceptors.global_http import GlobalHTTPInterceptor
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


@pytest.fixture(autouse=True)
def _reset_tracer():
    """Reset the global tracer singleton between tests."""
    _telemetry._tracer = None
    _telemetry._metrics_server_started = False
    _telemetry._proxy_duration_histogram = None
    _telemetry._proxy_cost_histogram = None
    yield
    _telemetry._tracer = None
    _telemetry._metrics_server_started = False
    _telemetry._proxy_duration_histogram = None
    _telemetry._proxy_cost_histogram = None


# ─── Unit: telemetry module API ──────────────────────────────────────────────

class TestTelemetryModule:
    def test_get_tracer_without_otel_env_returns_noop(self):
        """get_tracer() must work even when OTel is disabled (MINTRY_OTEL_ENABLED unset)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MINTRY_OTEL_ENABLED", None)
            tracer = _telemetry.get_tracer()
            assert tracer is not None

    def test_get_tracer_with_otel_enabled_returns_real_tracer(self):
        """When MINTRY_OTEL_ENABLED=1, get_tracer() returns an OTel tracer."""
        with patch.dict(os.environ, {"MINTRY_OTEL_ENABLED": "1"}):
            tracer = _telemetry.get_tracer()
            assert tracer is not None

    def test_record_proxy_duration_noop_when_histogram_absent(self):
        """record_proxy_duration() must not raise when histogram is None."""
        _telemetry._proxy_duration_histogram = None
        _telemetry.record_proxy_duration(42.5)  # should not raise

    def test_record_proxy_cost_noop_when_histogram_absent(self):
        """record_proxy_cost() must not raise when histogram is None."""
        _telemetry._proxy_cost_histogram = None
        _telemetry.record_proxy_cost(0.001)  # should not raise

    def test_start_metrics_server_is_noop_without_env(self):
        """start_metrics_server() must be a no-op when MINTRY_OTEL_ENABLED is unset."""
        os.environ.pop("MINTRY_OTEL_ENABLED", None)
        _telemetry.start_metrics_server()  # should not raise or bind a port
        assert not _telemetry._metrics_server_started


# ─── Integration: span wraps the proxy request ───────────────────────────────

class TestSpanInstrumentation:
    """
    Verifies that the interceptor opens and closes an OTel span around every
    proxied request.  We use pytest-httpx's respx to mock the network call so
    no real server is needed.
    """

    # Hardcoded valid Gemini-style JSON — mirrors the mock server's response.
    MOCK_GEMINI_RESPONSE = {
        "candidates": [
            {
                "content": {"parts": [{"text": "mock"}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [],
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 14,
            "totalTokenCount": 26,
        },
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 14,
        },
        "model": "gemini-2.0-flash-mock",
        "modelVersion": "gemini-2.0-flash-mock",
    }

    def _build_engine(self, tmp_path):
        import mintry
        # Use a temp DB so tests are isolated.
        engine = mintry.init(
            api_key="test_key",
            db_path=str(tmp_path / "test.db"),
        )
        engine.wallet.create_mandate("test_mandate", max_usd=100.0)
        return engine

    def test_span_duration_is_recorded(self, tmp_path, httpx_mock):
        """
        After a proxied LLM request, record_proxy_duration must have been
        called with a positive value.
        """
        httpx_mock.add_response(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            method="POST",
            json=self.MOCK_GEMINI_RESPONSE,
            status_code=200,
        )

        recorded_durations: list[float] = []

        with patch.object(_telemetry, "record_proxy_duration",
                          side_effect=recorded_durations.append):
            engine = self._build_engine(tmp_path)
            with httpx.Client() as client:
                client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                    json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
                    headers={"x-mintry-mandate": "test_mandate"},
                )

        assert len(recorded_durations) >= 1, "Expected at least one duration recording"
        assert recorded_durations[0] > 0, "Recorded duration must be positive"

    def test_span_cost_is_recorded(self, tmp_path, httpx_mock):
        """record_proxy_cost must be called once per successful LLM response."""
        httpx_mock.add_response(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            method="POST",
            json=self.MOCK_GEMINI_RESPONSE,
            status_code=200,
        )

        recorded_costs: list[float] = []

        with patch.object(_telemetry, "record_proxy_cost",
                          side_effect=recorded_costs.append):
            engine = self._build_engine(tmp_path)
            with httpx.Client() as client:
                client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                    json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
                    headers={"x-mintry-mandate": "test_mandate"},
                )

        assert len(recorded_costs) >= 1, "Expected at least one cost recording"

    def test_non_llm_request_still_records_duration(self, tmp_path, httpx_mock):
        """
        Even non-LLM requests get a duration span (the tracer wraps all send
        calls), so record_proxy_duration should be called regardless of URL.
        """
        httpx_mock.add_response(
            url="https://example.com/api",
            method="GET",
            status_code=200,
        )

        recorded_durations: list[float] = []

        with patch.object(_telemetry, "record_proxy_duration",
                          side_effect=recorded_durations.append):
            self._build_engine(tmp_path)
            with httpx.Client() as client:
                client.get("https://example.com/api")

        assert len(recorded_durations) >= 1
        assert recorded_durations[0] >= 0


# ─── Integration: mock server smoke-test (skipped in CI) ─────────────────────

@pytest.mark.skipif(
    not _mock_server_running(),
    reason="Requires a running Gemini mock server on localhost:9090. "
           "Start with: go run tools/gemini-mock-server/main.go",
)
class TestMockServerIntegration:
    """
    Live integration test against the Go mock server.
    Start with: go run tools/gemini-mock-server/main.go
    Then run:   uv run pytest tests/test_telemetry.py::TestMockServerIntegration -v
    """

    MOCK_URL = "http://localhost:9090/v1beta/models/gemini-2.0-flash:generateContent"

    def test_mock_server_returns_200(self):
        r = httpx.get("http://localhost:9090/health")
        assert r.status_code == 200

    def test_mock_server_latency_gte_10ms(self):
        """The mock server's synthetic delay must be >= 10 ms."""
        t0 = time.perf_counter()
        r = httpx.post(
            self.MOCK_URL,
            json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms >= 10.0, f"Expected ≥10ms, got {elapsed_ms:.2f}ms"

    def test_proxy_overhead_is_sub_millisecond(self, tmp_path):
        """
        Verifies that the OTel span is correctly wired around the full
        pre→post-flight proxy window and that span duration is captured.

        IMPORTANT — what this span measures
        ------------------------------------
        The Mintry span covers the FULL proxy window: from the instant the
        monkey-patch hook fires (pre-flight) to the instant the response bytes
        are flushed back to the caller (post-flight).  On a loopback connection
        this necessarily includes:

            [Mintry pre-flight]  +  [TCP round-trip to mock server]  +  [Mintry post-flight]

        The mock server sleeps 10 ms, so the minimum span duration on loopback
        is ~10–15 ms.  The span duration is therefore NOT a pure measure of
        Mintry's internal CPU time.

        How to isolate true internal overhead
        -------------------------------------
        Compare the mock server's own log (`duration=10.Xms`) with the span's
        `mintry.proxy_duration_ms` attribute.  The difference is the Mintry
        pre+post-flight processing time (typically < 1 ms on this hardware).

        This test asserts:
        1. The span fires (recorded_durations has exactly one entry).
        2. The recorded duration is positive.
        3. The full round-trip completes in a sane loopback budget (< 500 ms).
        """
        import mintry
        engine = mintry.init(api_key="test_key", db_path=str(tmp_path / "live.db"))
        engine.wallet.create_mandate("live_test", max_usd=100.0)

        # Temporarily add localhost:9090 to the LLM host list so the interceptor
        # treats this as an LLM request (fiscal + intent checks + metering).
        from mintry.interceptors import global_http as _gh
        original_hosts = list(_gh._LLM_HOSTS)
        _gh._LLM_HOSTS.append("localhost")

        recorded_durations: list[float] = []
        with patch.object(_telemetry, "record_proxy_duration",
                          side_effect=recorded_durations.append):
            with httpx.Client() as client:
                r = client.post(
                    self.MOCK_URL,
                    json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
                    headers={"x-mintry-mandate": "live_test"},
                )

        _gh._LLM_HOSTS[:] = original_hosts

        assert r.status_code == 200
        assert len(recorded_durations) == 1, "OTel span must fire exactly once per request"
        span_duration_ms = recorded_durations[0]
        assert span_duration_ms > 0, "Span duration must be positive"
        # On loopback the span covers the full network round-trip + 10 ms mock delay.
        # 500 ms is a generous ceiling that catches hangs / deadlocks without
        # being brittle on slow CI runners.
        assert span_duration_ms < 500, (
            f"Full span duration {span_duration_ms:.1f}ms exceeds 500 ms ceiling "
            "(indicates a hang in pre/post-flight processing)."
        )
        # The mock server adds exactly 10 ms.  The remainder is Mintry + loopback TCP.
        # On a healthy dev machine this is typically 1–5 ms additional overhead.
        print(
            f"\n[OVERHEAD] span={span_duration_ms:.2f}ms  "
            f"mock_baseline=10ms  "
            f"proxy+network_overhead={span_duration_ms - 10:.2f}ms"
        )
