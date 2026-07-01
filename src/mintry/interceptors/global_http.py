import httpx
import sys
import json
import os
import time
import queue
import threading
from datetime import datetime, timezone

from mintry.core.pricing import calculate_cost
from mintry.core.exceptions import MintryMandateExceeded
from mintry import telemetry as _telemetry

_METERING_QUEUE = queue.Queue()
_METERING_THREAD = None
_METERING_THREAD_STARTED = False
_METERING_THREAD_LOCK = threading.Lock()


def _run_metering_worker():
    while True:
        engine, request_info, response_bytes = _METERING_QUEUE.get()
        try:
            _process_metering_task(engine, request_info, response_bytes)
        except Exception:
            pass
        finally:
            _METERING_QUEUE.task_done()


def _ensure_metering_worker():
    global _METERING_THREAD_STARTED, _METERING_THREAD
    if _METERING_THREAD_STARTED:
        return
    with _METERING_THREAD_LOCK:
        if _METERING_THREAD_STARTED:
            return
        _METERING_THREAD = threading.Thread(target=_run_metering_worker, daemon=True)
        _METERING_THREAD.start()
        _METERING_THREAD_STARTED = True


def _enqueue_metering(engine, request_info, response_bytes):
    _ensure_metering_worker()
    _METERING_QUEUE.put((engine, request_info, response_bytes))


def _flush_metering_queue(timeout: float = 3.0) -> None:
    """Block until all pending metering tasks have been processed."""
    _METERING_QUEUE.join()


def _extract_model_from_info(request_info):
    url = request_info.get("url", "")
    if "/models/" in url:
        parts = url.split("/models/")[-1].split(":")
        if parts:
            return parts[0]

    try:
        body = json.loads(request_info.get("content") or b"")
        return body.get("model", "unknown")
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return "unknown"


def _process_metering_task(engine, request_info, response_bytes):
    try:
        data = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    model = data.get("model") or _extract_model_from_info(request_info)
    prompt_tokens, completion_tokens = _extract_tokens(data)
    actual_cost = calculate_cost(model, prompt_tokens, completion_tokens)
    engine.wallet.record_usage(request_info["mandate_id"], actual_cost)
    _telemetry.record_proxy_cost(actual_cost)

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


def _extract_tokens(data: dict) -> tuple[int, int]:
    """Extract input and output tokens supporting standard (OpenAI/Anthropic/Mistral) and Gemini formats."""
    usage = data.get("usage")
    if isinstance(usage, dict):
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    
    usage_metadata = data.get("usageMetadata")
    if isinstance(usage_metadata, dict):
        return usage_metadata.get("promptTokenCount", 0), usage_metadata.get("candidatesTokenCount", 0)
        
    return 0, 0


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

                # 4. POST-FLIGHT — Defer metering off the critical response path.
                if response.status_code == 200 and is_llm:
                    content = response.content
                    request_info = {
                        "url": url_str,
                        "content": request.content,
                        "mandate_id": mandate_id,
                    }
                    _enqueue_metering(engine, request_info, content)
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

                # 4. POST-FLIGHT — Defer metering off the critical response path.
                if response.status_code == 200 and is_llm:
                    content = await response.aread()
                    request_info = {
                        "url": url_str,
                        "content": request.content,
                        "mandate_id": mandate_id,
                    }
                    _enqueue_metering(engine, request_info, content)
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