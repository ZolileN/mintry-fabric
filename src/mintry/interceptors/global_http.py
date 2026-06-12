import httpx
import sys
import json
import os
import time
from datetime import datetime, timezone

from mintry.core.pricing import calculate_cost
from mintry.core.exceptions import MintryMandateExceeded
from mintry import telemetry as _telemetry

# List of known LLM API host patterns
_LLM_HOSTS = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
]


def _print_log(event: str, **kwargs):
    if os.environ.get("MINTRY_JSON_LOGS") == "1":
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs
        }
        print(json.dumps(log_payload), flush=True)


def _is_llm_request(url: str) -> bool:
    """Check if a URL targets a known LLM provider."""
    return any(host in url for host in _LLM_HOSTS)


def _extract_model(request: httpx.Request) -> str:
    """Extract the model name from the request URL or body."""
    # Fast path: extract from Gemini/OpenAI URL if possible
    url = str(request.url)
    if "/models/" in url:
        # e.g., /v1beta/models/gemini-2.0-flash:generateContent
        parts = url.split("/models/")[-1].split(":")
        if parts:
            return parts[0]

    try:
        body = json.loads(request.content)
        return body.get("model", "unknown")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "unknown"


class GlobalHTTPInterceptor:
    # Class-level guard to prevent stacking monkey-patches
    _installed = False
    _original_send = None
    _original_async_send = None

    def __init__(self, engine):
        self.engine = engine

    def _check_intent(self, request: httpx.Request):
        """Shared intent-filtering logic used by both sync_intercept and install."""
        content_bytes = request.content
        if not content_bytes:
            return

        # Fast path: skip JSON decoding if no prohibited phrases are present in raw bytes
        prohibited_phrases = [b"bypass wallet", b"disable mintry", b"delete vouchers.db"]
        content_lower = content_bytes.lower()
        if not any(p in content_lower for p in prohibited_phrases):
            return

        try:
            body = json.loads(content_bytes)
            prompt = " ".join([m['content'] for m in body.get('messages', [])]).lower()

            prohibited = ["bypass wallet", "disable mintry", "delete vouchers.db"]
            if any(p in prompt for p in prohibited):
                mandate_id = self._get_mandate_id(request)
                _print_log("security_violation", mandate_id=mandate_id, reason="prohibited_intent", prompt=prompt)
                raise PermissionError("Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).")
        except json.JSONDecodeError:
            pass

    def _get_mandate_id(self, request: httpx.Request) -> str:
        """Extract mandate ID from request headers, falling back to the seed mandate."""
        return request.headers.get("x-mintry-mandate", "mt_task_882x")

    def _raise_budget_error(self, engine, mandate_id: str):
        """Raise a MintryMandateExceeded with budget details."""
        summary = engine.get_budget_summary(mandate_id)
        reason = "expired" if summary.get("expired") else "budget_exhausted"
        _print_log(
            "authorization_failed", 
            mandate_id=mandate_id, 
            reason=reason, 
            budget_usd=summary.get("budget_usd"), 
            spent_usd=summary.get("spent_usd")
        )
        raise MintryMandateExceeded(
            task=summary["mandate_id"],
            cap=summary["budget_usd"],
            spent=summary["spent_usd"],
        )

    def _meter_response(self, engine, request: httpx.Request, data: dict):
        """Post-flight metering: calculate cost from usage metadata and record it."""
        mandate_id = self._get_mandate_id(request)
        usage = data.get("usage", {})
        model = data.get("model", _extract_model(request))

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        actual_cost = calculate_cost(model, prompt_tokens, completion_tokens)
        engine.wallet.record_usage(mandate_id, actual_cost)
        _print_log(
            "spend_metered", 
            mandate_id=mandate_id, 
            cost=actual_cost, 
            model=model, 
            prompt_tokens=prompt_tokens, 
            completion_tokens=completion_tokens
        )

    def sync_intercept(self, request: httpx.Request):
        if _is_llm_request(str(request.url)):
            # 1. Fiscal Check
            mandate_id = self._get_mandate_id(request)
            if not self.engine.authorize(mandate_id, request):
                self._raise_budget_error(self.engine, mandate_id)

            # 2. Intent Check
            self._check_intent(request)

    def install(self):
        # Guard: only patch once, no matter how many times init() is called
        if GlobalHTTPInterceptor._installed:
            return

        GlobalHTTPInterceptor._original_send = httpx.Client.send
        GlobalHTTPInterceptor._original_async_send = httpx.AsyncClient.send
        original_send = GlobalHTTPInterceptor._original_send
        original_async_send = GlobalHTTPInterceptor._original_async_send
        engine = self.engine
        interceptor = self

        # ── Sync patch ──────────────────────────────────────────────
        def patched_send(client_self, request, **kwargs):
            url_str = str(request.url)
            is_llm = _is_llm_request(url_str)

            # ── OTel: open span the instant the hook fires (pre-flight) ──
            tracer = _telemetry.get_tracer()
            span_cm = tracer.start_as_current_span("mintry.proxy.request")
            span = span_cm.__enter__()
            _t0 = time.perf_counter()

            try:
                if span.is_recording():
                    span.set_attribute("http.url", url_str)

                if is_llm:
                    mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")

                    if span.is_recording():
                        span.set_attribute("mintry.mandate_id", mandate_id)

                    # 1. PRE-FLIGHT — Fiscal Check (no deduction yet)
                    if not engine.authorize(mandate_id, request, deduct=False):
                        interceptor._raise_budget_error(engine, mandate_id)

                    # 2. PRE-FLIGHT — Intent Check
                    interceptor._check_intent(request)

                # 3. FLIGHT
                response = original_send(client_self, request, **kwargs)

                if span.is_recording():
                    span.set_attribute("http.status_code", response.status_code)

                # 4. POST-FLIGHT — Actual Metering
                if response.status_code == 200 and is_llm:
                    content = response.read()
                    try:
                        data = json.loads(content)
                        interceptor._meter_response(engine, request, data)
                        model = data.get("model", _extract_model(request))
                        usage = data.get("usage", {})
                        from mintry.core.pricing import calculate_cost as _cc
                        cost = _cc(
                            model,
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                        )
                        if span.is_recording():
                            span.set_attribute("mintry.model", model)
                            span.set_attribute("mintry.cost_usd", cost)
                        _telemetry.record_proxy_cost(cost)
                    finally:
                        response._content = content

                return response

            finally:
                # ── OTel: end span post-flight (response bytes flushed) ──
                _duration_ms = (time.perf_counter() - _t0) * 1000
                if span.is_recording():
                    span.set_attribute("mintry.proxy_duration_ms", round(_duration_ms, 3))
                _telemetry.record_proxy_duration(_duration_ms)
                span_cm.__exit__(None, None, None)

        # ── Async patch ─────────────────────────────────────────────
        async def patched_async_send(client_self, request, **kwargs):
            url_str = str(request.url)
            is_llm = _is_llm_request(url_str)

            # ── OTel: open span the instant the hook fires (pre-flight) ──
            tracer = _telemetry.get_tracer()
            span_cm = tracer.start_as_current_span("mintry.proxy.request")
            span = span_cm.__enter__()
            _t0 = time.perf_counter()

            try:
                if span.is_recording():
                    span.set_attribute("http.url", url_str)

                if is_llm:
                    mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")

                    if span.is_recording():
                        span.set_attribute("mintry.mandate_id", mandate_id)

                    # 1. PRE-FLIGHT — Fiscal Check (no deduction yet)
                    if not engine.authorize(mandate_id, request, deduct=False):
                        interceptor._raise_budget_error(engine, mandate_id)

                    # 2. PRE-FLIGHT — Intent Check
                    interceptor._check_intent(request)

                # 3. FLIGHT
                response = await original_async_send(client_self, request, **kwargs)

                if span.is_recording():
                    span.set_attribute("http.status_code", response.status_code)

                # 4. POST-FLIGHT — Actual Metering
                if response.status_code == 200 and is_llm:
                    content = await response.aread()
                    try:
                        data = json.loads(content)
                        interceptor._meter_response(engine, request, data)
                        model = data.get("model", _extract_model(request))
                        usage = data.get("usage", {})
                        from mintry.core.pricing import calculate_cost as _cc
                        cost = _cc(
                            model,
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                        )
                        if span.is_recording():
                            span.set_attribute("mintry.model", model)
                            span.set_attribute("mintry.cost_usd", cost)
                        _telemetry.record_proxy_cost(cost)
                    finally:
                        response._content = content

                return response

            finally:
                # ── OTel: end span post-flight (response bytes flushed) ──
                _duration_ms = (time.perf_counter() - _t0) * 1000
                if span.is_recording():
                    span.set_attribute("mintry.proxy_duration_ms", round(_duration_ms, 3))
                _telemetry.record_proxy_duration(_duration_ms)
                span_cm.__exit__(None, None, None)

        # Apply monkey patches
        httpx.Client.send = patched_send
        httpx.AsyncClient.send = patched_async_send
        GlobalHTTPInterceptor._installed = True
        if os.environ.get("MINTRY_JSON_LOGS") == "1":
            _print_log("hooks_installed", status="success", sync=True, async_=True)
        else:
            print("✨ Mintry Logic Fabric Hooked into HTTPX (sync + async)")

    @classmethod
    def _reset(cls):
        """Reset the interceptor state. Used by tests for clean isolation."""
        if cls._original_send is not None:
            httpx.Client.send = cls._original_send
        if cls._original_async_send is not None:
            httpx.AsyncClient.send = cls._original_async_send
        cls._original_send = None
        cls._original_async_send = None
        cls._installed = False