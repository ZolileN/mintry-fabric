# src/mintry/telemetry.py
"""
Mintry Fabric — OpenTelemetry & Prometheus telemetry bootstrap.

Activation
----------
Set ``MINTRY_OTEL_ENABLED=1`` before calling ``mintry.init()``.

Metrics endpoint
----------------
A Prometheus-compatible ``/metrics`` HTTP endpoint is started on
``MINTRY_METRICS_PORT`` (default 9091).  Point your Prometheus scrape config
at ``http://localhost:9091/metrics``.

Spans
-----
Every proxied LLM request produces a span named ``mintry.proxy.request`` with
the following attributes:

    http.url            — upstream URL
    http.status_code    — response status (set post-flight)
    mintry.mandate_id   — mandate that authorised the request
    mintry.model        — LLM model name extracted from the request body
    mintry.cost_usd     — spend recorded for this call (set post-flight)

The span duration is measured from the microsecond the Mintry hook fires (pre-
flight) to the microsecond the response bytes are flushed back to the caller.
This is the true internal proxy processing time.

Histograms
----------
    mintry_proxy_duration_ms  — internal proxy latency (pre→post-flight)
    mintry_proxy_cost_usd     — per-request LLM spend
"""

from __future__ import annotations

import os
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — only pulled in when MINTRY_OTEL_ENABLED=1 so that the core
# SDK remains lightweight for users who do not need observability.
# ---------------------------------------------------------------------------

_tracer = None
_metrics_server_started = False
_lock = threading.Lock()

# Prometheus histogram objects (created once on first use)
_proxy_duration_histogram = None
_proxy_cost_histogram = None


def _otel_enabled() -> bool:
    return os.environ.get("MINTRY_OTEL_ENABLED", "0") == "1"


def _get_metrics_port() -> int:
    return int(os.environ.get("MINTRY_METRICS_PORT", "9091"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tracer():
    """Return the Mintry OTel tracer, initialising it on first call.

    If MINTRY_OTEL_ENABLED is not set, returns a no-op tracer so the
    interceptor code path is unchanged.
    """
    global _tracer

    if _tracer is not None:
        return _tracer

    with _lock:
        if _tracer is not None:
            return _tracer

        if not _otel_enabled():
            # Return a no-op tracer that has the same API surface
            from opentelemetry import trace
            _tracer = trace.get_tracer("mintry.noop")
            return _tracer

        # Full OTel initialisation
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider()

        # Console exporter — spans are human-readable on stdout when
        # MINTRY_OTEL_CONSOLE_SPANS=1.  Disabled by default to keep logs clean.
        if os.environ.get("MINTRY_OTEL_CONSOLE_SPANS") == "1":
            provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("mintry.fabric", "1.0.0")
        logger.info("Mintry OTel tracer initialised")
        return _tracer


def start_metrics_server() -> None:
    """Start the Prometheus /metrics HTTP server in a daemon thread.

    Safe to call multiple times — only one server is started.
    """
    global _metrics_server_started, _proxy_duration_histogram, _proxy_cost_histogram

    if not _otel_enabled():
        return

    with _lock:
        if _metrics_server_started:
            return

        try:
            from prometheus_client import (
                Histogram,
                start_http_server,
            )
        except ImportError as exc:
            logger.warning(
                "prometheus_client not installed — metrics endpoint disabled. "
                "Run: uv add prometheus_client  (%s)", exc
            )
            return

        port = _get_metrics_port()

        # Proxy internal latency: from pre-flight hook to post-flight flush.
        _proxy_duration_histogram = Histogram(
            "mintry_proxy_duration_ms",
            "Internal Mintry proxy latency in milliseconds (pre→post-flight)",
            buckets=[0.5, 1, 2, 5, 10, 15, 20, 30, 50, 100, 250, 500, 1000],
        )

        # Per-request LLM cost.
        _proxy_cost_histogram = Histogram(
            "mintry_proxy_cost_usd",
            "Per-request LLM spend in USD recorded by Mintry",
            buckets=[0.000001, 0.00001, 0.0001, 0.001, 0.01, 0.1, 1.0],
        )

        # Start the metrics HTTP server in a daemon thread so it does not
        # block the main application.
        start_http_server(port)
        _metrics_server_started = True
        logger.info("Mintry Prometheus metrics available at http://localhost:%d/metrics", port)
        print(f"📊 Mintry metrics: http://localhost:{port}/metrics")


def record_proxy_duration(duration_ms: float) -> None:
    """Record a proxy round-trip duration (milliseconds)."""
    if _proxy_duration_histogram is not None:
        _proxy_duration_histogram.observe(duration_ms)


def record_proxy_cost(cost_usd: float) -> None:
    """Record a per-request LLM cost (USD)."""
    if _proxy_cost_histogram is not None:
        _proxy_cost_histogram.observe(cost_usd)


def span_context(span_name: str = "mintry.proxy.request"):
    """Context manager that opens an OTel span and records its duration.

    Usage::

        with span_context() as span:
            span.set_attribute("http.url", url)
            response = do_work()
        # span is ended automatically

    Returns a no-op context if OTel is disabled.
    """
    tracer = get_tracer()
    return tracer.start_as_current_span(span_name)
