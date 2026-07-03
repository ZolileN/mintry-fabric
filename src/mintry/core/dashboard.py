import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from typing import ClassVar, Optional

from concurrent.futures import ThreadPoolExecutor

class ThreadPoolHTTPServer(HTTPServer):
    """Multi-threaded HTTP server using a fixed size thread pool to prevent thread/GIL thrashing."""
    request_queue_size = 65536  # Increase TCP backlog to handle massive concurrent VUs
    def __init__(self, server_address, RequestHandlerClass, max_workers=256):
        super().__init__(server_address, RequestHandlerClass)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def process_request(self, request, client_address):
        self.executor.submit(self.process_request_thread, request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

# Thread-local HTTPX client to completely eliminate connection pool lock contention
_thread_local = threading.local()

def get_proxy_client():
    if not hasattr(_thread_local, "client"):
        import httpx
        # Low limits per thread are sufficient as each thread runs sequentially
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0)
        _thread_local.client = httpx.Client(limits=limits, timeout=10.0)
    return _thread_local.client

def _is_integration_test_mandate(mandate_id: str) -> bool:
    """Filter integration-test mandate IDs from prospect-visible dashboard views."""
    lowered = mandate_id.lower()
    if lowered.startswith("kill_switch_"):
        return True
    if lowered in ("smoke_task", "new-agent", "test agent", "mt_task_882x"):
        return True
    if re.search(r"test.*agent|agent.*test", lowered):
        return True
    return False


def _should_hide_test_mandates() -> bool:
    """When MINTRY_DEMO_MODE=1, hide integration-test mandate rows from dashboard."""
    return os.getenv("MINTRY_DEMO_MODE", "").lower() in ("1", "true", "yes")


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    db_path: ClassVar[str | None] = None
    dashboard_ui_origin: ClassVar[str] = "http://127.0.0.1:3000"
    policy_cache: ClassVar[Optional[object]] = None  # PolicyCache instance
    control_plane: ClassVar[Optional[object]] = None  # SupabaseControlPlaneClient instance

    def log_message(self, format, *args):
        # Override to suppress standard HTTP logging to keep console clean
        pass

    def send_json_response(self, data, status_code=200):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(response_bytes)))
        try:
            self.end_headers()
            self.wfile.write(response_bytes)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_proxy(self, method: str):
        # 1. Read request headers and body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        
        # 2. Extract headers. Forward x-mintry-mandate and other headers.
        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                headers[k] = v

        # 3. Determine upstream URL. Default is localhost:9090 (the mock server).
        upstream_base = os.getenv("MINTRY_UPSTREAM_URL", "http://localhost:9090")
        upstream_url = f"{upstream_base}{self.path}"
        
        # 4. Make the call using the shared httpx.Client (monkey-patched by Mintry)
        try:
            client = get_proxy_client()
            req = client.build_request(
                method=method,
                url=upstream_url,
                content=body,
                headers=headers
            )
            response = client.send(req)
                
            # 5. Write the response back
            self.send_response(response.status_code)
            for k, v in response.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)
            
        except Exception as e:
            # If Mintry blocked the request due to budget limit / intent, handle it.
            # Usually, the exception is raised in pre-flight. We want to return
            # a proper error status back to the client (e.g. 402/403 for budget).
            from mintry.core.exceptions import MintryMandateExceeded
            if isinstance(e, MintryMandateExceeded):
                self.send_json_response({
                    "error": "Payment Required",
                    "message": str(e)
                }, 402)
            elif isinstance(e, PermissionError):
                self.send_json_response({
                    "error": "Forbidden",
                    "message": str(e)
                }, 403)
            else:
                self.send_json_response({"error": f"Proxy error: {str(e)}"}, 500)

    def do_GET(self):
        if self.path == "/":
            self.serve_root()
        elif self.path == "/api/summary":
            self.serve_api()
        elif self.path.startswith("/v1beta/models/"):
            self.handle_proxy("GET")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path.startswith("/v1beta/models/"):
            self.handle_proxy("POST")
            return

        if not self.db_path:
            self.send_error(500, "Database path not configured.")
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
        except Exception as e:
            self.send_json_response({"error": "Invalid JSON: " + str(e)}, 400)
            return

        from mintry.core.wallet import MintryWallet
        from datetime import datetime
        wallet = MintryWallet(db_path=self.db_path)

        if self.path == "/api/mandates/upsert":
            mandate_id = payload.get("id")
            budget_usd = payload.get("budget_usd")
            expires_at_str = payload.get("expires_at")
            
            if not mandate_id or budget_usd is None:
                self.send_json_response({"error": "Missing 'id' or 'budget_usd'"}, 400)
                return

            expires_at = None
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                except ValueError:
                    self.send_json_response({"error": "Invalid date format for 'expires_at'. Use ISO8601."}, 400)
                    return

            try:
                existing = wallet.get_mandate(mandate_id)
                if existing.get("status") == "unknown":
                    wallet.create_mandate(mandate_id, float(budget_usd), expires_at=expires_at)
                else:
                    wallet.update_mandate(mandate_id, float(budget_usd), expires_at=expires_at, status="active")
                
                self.send_json_response({"success": True}, 200)
            except Exception as e:
                self.send_json_response({"error": str(e)}, 500)

        elif self.path == "/api/mandates/revoke":
            mandate_id = payload.get("id")
            if not mandate_id:
                self.send_json_response({"error": "Missing mandate 'id'"}, 400)
                return
                
            try:
                wallet.exhaust_mandate(mandate_id)
                self.send_json_response({"success": True}, 200)
            except Exception as e:
                self.send_json_response({"error": str(e)}, 500)
        else:
            self.send_error(404, "Not Found")

    def serve_root(self):
        self.send_response(307)
        self.send_header("Location", self.dashboard_ui_origin)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def serve_api(self):
        if not self.db_path:
            self.send_error(500, "Database path not configured.")
            return

        try:
            data = self.get_stats_data()
            self.send_json_response(data, 200)
        except Exception as e:
            self.send_json_response({"error": str(e)}, 500)

    def get_stats_data(self) -> dict:
        db_resolved = Path(self.db_path).expanduser()
        # Ensure schema migrations and seed tables exist before raw summary reads.
        from mintry.core.wallet import MintryWallet
        wallet = MintryWallet(db_path=str(db_resolved))
        wallet.flush()
        conn = sqlite3.connect(db_resolved)
        try:
            mandates_rows = conn.execute(
                "SELECT id, max_usd, spent_usd, status, expires_at FROM mandates ORDER BY spent_usd DESC"
            ).fetchall()

            if _should_hide_test_mandates():
                mandates_rows = [r for r in mandates_rows if not _is_integration_test_mandate(r[0])]

            has_expiry = any(r[4] for r in mandates_rows)

            mandates = [
                {
                    "id": r[0],
                    "budget_usd": r[1],
                    "spent_usd": r[2],
                    "remaining_headroom": round((r[1] or 0.0) - (r[2] or 0.0), 4),
                    "status": "exhausted" if (r[2] or 0.0) >= (r[1] or 0.0) else r[3],
                    "expires_at": r[4] if r[4] else None,
                }
                for r in mandates_rows
            ]

            visible_ids = {m["id"] for m in mandates}
            total_budget = sum(m["budget_usd"] or 0.0 for m in mandates)
            total_spent = sum(m["spent_usd"] or 0.0 for m in mandates)
            total_mandates = len(mandates)
            
            # Top mandates
            top_mandates = [
                {"id": m["id"], "spent_usd": m["spent_usd"]}
                for m in sorted(mandates, key=lambda x: x["spent_usd"], reverse=True)[:5]
            ]
            
            # Recent history
            history_rows = conn.execute(
                "SELECT id, timestamp, mandate_id, action, amount, details FROM mandate_audit_log ORDER BY id DESC LIMIT 100"
            ).fetchall()
            history = [
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "mandate_id": r[2],
                    "action": r[3],
                    "amount": r[4],
                    "details": r[5]
                }
                for r in history_rows
                if r[2] in visible_ids or not _should_hide_test_mandates()
            ]

            block_actions = {"block", "exhaust", "expire"}
            requests_blocked = sum(1 for h in history if h["action"] in block_actions)
            overspend_prevented = round(
                sum(abs(h["amount"] or 0.0) for h in history if h["action"] == "block"),
                4,
            )
            
            return {
                "stats": {
                    "total_mandates": total_mandates,
                    "total_budget": round(total_budget, 4),
                    "total_spent": round(total_spent, 4),
                    "remaining_headroom": round(total_budget - total_spent, 4),
                    "protected_spend": round(total_spent, 4),
                    "requests_blocked": requests_blocked,
                    "overspend_prevented": overspend_prevented,
                    "active_agents": sum(1 for m in mandates if m["status"] == "active"),
                },
                "top_mandates": top_mandates,
                "mandates": mandates,
                "history": history,
                "has_expiry": False,
                "policy_sync": self._get_policy_sync_status(),
            }
        finally:
            conn.close()

    @classmethod
    def _get_policy_sync_status(cls) -> dict:
        """Get policy sync status from the policy cache (Principle 4: visible staleness)."""
        if not cls.policy_cache:
            return {
                "policy_version": None,
                "last_synced_at": None,
                "last_sync_error": None,
                "control_plane_healthy": False,
            }

        sync_status = cls.policy_cache.get_sync_status()
        control_plane_healthy = cls.control_plane.health_check() if cls.control_plane else False

        return {
            "policy_version": sync_status.get("policy_version"),
            "last_synced_at": sync_status.get("last_synced_at"),
            "last_sync_error": sync_status.get("last_sync_error"),
            "control_plane_healthy": control_plane_healthy,
        }

def start_dashboard(db_path: str, host: str = "127.0.0.1", port: int = 8000):
    """Starts the local web server hosting the dashboard."""
    # Enable HTTP/1.1 keep-alive for the high-concurrency production dashboard
    DashboardHandler.protocol_version = "HTTP/1.1"
    # Class-level assignment so the request handler knows which DB to query
    DashboardHandler.db_path = db_path
    DashboardHandler.dashboard_ui_origin = os.getenv(
        "MINTRY_DASHBOARD_UI_ORIGIN",
        DashboardHandler.dashboard_ui_origin,
    )
    
    # Initialize mintry global interceptor & telemetry metrics if MINTRY_OTEL_ENABLED=1
    # We must call init() to hook httpx and start Prometheus server.
    import mintry
    try:
        api_key = os.environ.get("MINTRY_API_KEY", "mk_dashboard_dev_key")
        # Ensure the mock server is recognized as an LLM host by Mintry's interceptor
        from mintry.interceptors import global_http as _gh
        if "localhost" not in _gh._LLM_HOSTS:
            _gh._LLM_HOSTS.append("localhost")
        if "127.0.0.1" not in _gh._LLM_HOSTS:
            _gh._LLM_HOSTS.append("127.0.0.1")
        
        engine = mintry.init(api_key=api_key, db_path=db_path)
        
        # Attach policy cache and control plane to dashboard handler for sync status
        DashboardHandler.policy_cache = getattr(engine, "policy_cache", None)
        DashboardHandler.control_plane = getattr(engine, "control_plane", None)
    except Exception as e:
        print(f"Warning: Failed to auto-initialize Mintry Logic Fabric in dashboard: {e}")

    server = ThreadPoolHTTPServer((host, port), DashboardHandler, max_workers=2048)
    print(f"✨ Mintry Observability Dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        server.server_close()
