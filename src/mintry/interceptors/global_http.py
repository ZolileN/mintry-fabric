import httpx
import sys
import json

class GlobalHTTPInterceptor:
    def __init__(self, engine):
        self.engine = engine

    def sync_intercept(self, request: httpx.Request):
        if "openai.com" in str(request.url):
            # 1. Fiscal Check
            if not self.engine.authorize("mt_task_882x", request):
                raise PermissionError("Mintry Logic Fabric: Budget Exhausted.")
            
            # 2. Intent Check (New)
            try:
                body = json.loads(request.content)
                prompt = " ".join([m['content'] for m in body.get('messages', [])]).lower()
                
                prohibited = ["bypass wallet", "disable mintry", "delete vouchers.db"]
                if any(p in prompt for p in prohibited):
                    raise PermissionError("Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).")
            except json.JSONDecodeError:
                pass

    def install(self):
        original_send = httpx.Client.send

        def patched_send(client_self, request, **kwargs):
            # 1. PRE-FLIGHT (Fiscal Check only)
            if "api.openai.com" in str(request.url):
                # pass deduct=False here!
                if not self.engine.authorize("mt_task_882x", request, deduct=False):
                    raise PermissionError("Mintry Logic Fabric: Budget Exhausted.")

            # 2. FLIGHT
            response = original_send(client_self, request, **kwargs)

            # 3. POST-FLIGHT (Actual Metering)
            if response.status_code == 200 and "api.openai.com" in str(request.url):
                content = response.read()
                try:
                    data = json.loads(content)
                    usage = data.get("usage", {})
                    # Calculate: 2000 tokens * 0.000005 = $0.01
                    actual_cost = (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)) * 0.000005
                    
                    # This is now the ONLY place where record_usage is called
                    self.engine.wallet.record_usage("mt_task_882x", actual_cost)
                finally:
                    response._content = content
            
            return response
            # --- END OF INDENTED BLOCK ---

        # Apply the monkey patch
        httpx.Client.send = patched_send
        print("✨ Mintry Logic Fabric Hooked into HTTPX")