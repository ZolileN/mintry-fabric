import httpx
import sys
import json

class GlobalHTTPInterceptor:
    # Class-level guard to prevent stacking monkey-patches
    _installed = False
    _original_send = None

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

    def sync_intercept(self, request: httpx.Request):
        if "openai.com" in str(request.url):
            # 1. Fiscal Check
            mandate_id = self._get_mandate_id(request)
            if not self.engine.authorize(mandate_id, request):
                summary = self.engine.get_budget_summary(mandate_id)
                raise PermissionError(
                    f"Mintry Logic Fabric: Budget Exhausted for mandate '{summary['mandate_id']}'. "
                    f"Budget: ${summary['budget_usd']:.4f} | Spent: ${summary['spent_usd']:.4f} | "
                    f"Remaining: ${summary['remaining_usd']:.4f} (minimum $0.01 required)"
                )

            # 2. Intent Check
            self._check_intent(request)

    def install(self):
        # Guard: only patch once, no matter how many times init() is called
        if GlobalHTTPInterceptor._installed:
            return

        GlobalHTTPInterceptor._original_send = httpx.Client.send
        original_send = GlobalHTTPInterceptor._original_send
        engine = self.engine

        def patched_send(client_self, request, **kwargs):
            if "api.openai.com" in str(request.url):
                mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")

                # 1. PRE-FLIGHT — Fiscal Check (no deduction yet)
                if not engine.authorize(mandate_id, request, deduct=False):
                    summary = engine.get_budget_summary(mandate_id)
                    raise PermissionError(
                        f"Mintry Logic Fabric: Budget Exhausted for mandate '{summary['mandate_id']}'. "
                        f"Budget: ${summary['budget_usd']:.4f} | Spent: ${summary['spent_usd']:.4f} | "
                        f"Remaining: ${summary['remaining_usd']:.4f} (minimum $0.01 required)"
                    )

                # 2. PRE-FLIGHT — Intent Check
                try:
                    body = json.loads(request.content)
                    prompt = " ".join([m['content'] for m in body.get('messages', [])]).lower()

                    prohibited = ["bypass wallet", "disable mintry", "delete vouchers.db"]
                    if any(p in prompt for p in prohibited):
                        raise PermissionError("Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).")
                except json.JSONDecodeError:
                    pass

            # 3. FLIGHT
            response = original_send(client_self, request, **kwargs)

            # 4. POST-FLIGHT — Actual Metering
            if response.status_code == 200 and "api.openai.com" in str(request.url):
                mandate_id = request.headers.get("x-mintry-mandate", "mt_task_882x")
                content = response.read()
                try:
                    data = json.loads(content)
                    usage = data.get("usage", {})
                    # Calculate: 2000 tokens * 0.000005 = $0.01
                    actual_cost = (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)) * 0.000005

                    # This is now the ONLY place where record_usage is called
                    engine.wallet.record_usage(mandate_id, actual_cost)
                finally:
                    response._content = content

            return response

        # Apply the monkey patch
        httpx.Client.send = patched_send
        GlobalHTTPInterceptor._installed = True
        print("✨ Mintry Logic Fabric Hooked into HTTPX")

    @classmethod
    def _reset(cls):
        """Reset the interceptor state. Used by tests for clean isolation."""
        if cls._original_send is not None:
            httpx.Client.send = cls._original_send
        cls._original_send = None
        cls._installed = False