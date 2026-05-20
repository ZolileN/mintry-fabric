import httpx
import sys
import json

from mintry.core.pricing import calculate_cost

# List of known LLM API host patterns
_LLM_HOSTS = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
]


def _is_llm_request(url: str) -> bool:
    """Check if a URL targets a known LLM provider."""
    return any(host in url for host in _LLM_HOSTS)


def _extract_model(request: httpx.Request) -> str:
    """Extract the model name from the request body."""
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
        try:
            body = json.loads(request.content)
            prompt = " ".join([m['content'] for m in body.get('messages', [])]).lower()

            prohibited = ["bypass wallet", "disable mintry", "delete vouchers.db"]
            if any(p in prompt for p in prohibited):
                raise PermissionError("Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).")
        except json.JSONDecodeError:
            pass

    def _get_mandate_id(self, request: httpx.Request) -> str:
        """Extract mandate ID from request headers, falling back to the seed mandate."""
        return request.headers.get("x-mintry-mandate", "mt_task_882x")

    def _raise_budget_error(self, engine, mandate_id: str):
        """Raise a PermissionError with budget details."""
        summary = engine.get_budget_summary(mandate_id)
        if summary.get("expired"):
            raise PermissionError(
                f"Mintry Logic Fabric: Mandate '{summary['mandate_id']}' has expired. "
                f"Budget: ${summary['budget_usd']:.4f} | Spent: ${summary['spent_usd']:.4f}"
            )
        raise PermissionError(
            f"Mintry Logic Fabric: Budget Exhausted for mandate '{summary['mandate_id']}'. "
            f"Budget: ${summary['budget_usd']:.4f} | Spent: ${summary['spent_usd']:.4f} | "
            f"Remaining: ${summary['remaining_usd']:.4f} (minimum $0.01 required)"
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
            if _is_llm_request(url_str):
                mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")

                # 1. PRE-FLIGHT — Fiscal Check (no deduction yet)
                if not engine.authorize(mandate_id, request, deduct=False):
                    interceptor._raise_budget_error(engine, mandate_id)

                # 2. PRE-FLIGHT — Intent Check
                interceptor._check_intent(request)

            # 3. FLIGHT
            response = original_send(client_self, request, **kwargs)

            # 4. POST-FLIGHT — Actual Metering
            if response.status_code == 200 and _is_llm_request(url_str):
                content = response.read()
                try:
                    data = json.loads(content)
                    interceptor._meter_response(engine, request, data)
                finally:
                    response._content = content

            return response

        # ── Async patch ─────────────────────────────────────────────
        async def patched_async_send(client_self, request, **kwargs):
            url_str = str(request.url)
            if _is_llm_request(url_str):
                mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")

                # 1. PRE-FLIGHT — Fiscal Check (no deduction yet)
                if not engine.authorize(mandate_id, request, deduct=False):
                    interceptor._raise_budget_error(engine, mandate_id)

                # 2. PRE-FLIGHT — Intent Check
                interceptor._check_intent(request)

            # 3. FLIGHT
            response = await original_async_send(client_self, request, **kwargs)

            # 4. POST-FLIGHT — Actual Metering
            if response.status_code == 200 and _is_llm_request(url_str):
                content = await response.aread()
                try:
                    data = json.loads(content)
                    interceptor._meter_response(engine, request, data)
                finally:
                    response._content = content

            return response

        # Apply monkey patches
        httpx.Client.send = patched_send
        httpx.AsyncClient.send = patched_async_send
        GlobalHTTPInterceptor._installed = True
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