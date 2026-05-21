import json
import os
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from typing import ClassVar

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for handling concurrent dashboard requests."""
    daemon_threads = True

class DashboardHandler(BaseHTTPRequestHandler):
    db_path: ClassVar[str | None] = None
    dashboard_ui_origin: ClassVar[str] = "http://127.0.0.1:3000"

    def log_message(self, format, *args):
        # Override to suppress standard HTTP logging to keep console clean
        pass

    def do_GET(self):
        if self.path == "/":
            self.serve_root()
        elif self.path == "/api/summary":
            self.serve_api()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if not self.db_path:
            self.send_error(500, "Database path not configured.")
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON: " + str(e)}).encode("utf-8"))
            return

        from mintry.core.wallet import MintryWallet
        from datetime import datetime
        wallet = MintryWallet(db_path=self.db_path)

        if self.path == "/api/mandates/upsert":
            mandate_id = payload.get("id")
            budget_usd = payload.get("budget_usd")
            expires_at_str = payload.get("expires_at")
            
            if not mandate_id or budget_usd is None:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing 'id' or 'budget_usd'"}).encode("utf-8"))
                return

            expires_at = None
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                except ValueError:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Invalid date format for 'expires_at'. Use ISO8601."}).encode("utf-8"))
                    return

            try:
                existing = wallet.get_mandate(mandate_id)
                if existing.get("status") == "unknown":
                    wallet.create_mandate(mandate_id, float(budget_usd), expires_at=expires_at)
                else:
                    wallet.update_mandate(mandate_id, float(budget_usd), expires_at=expires_at, status="active")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        elif self.path == "/api/mandates/revoke":
            mandate_id = payload.get("id")
            if not mandate_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing mandate 'id'"}).encode("utf-8"))
                return
                
            try:
                wallet.exhaust_mandate(mandate_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def serve_root(self):
        self.send_response(307)
        self.send_header("Location", self.dashboard_ui_origin)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def serve_api(self):
        if not self.db_path:
            self.send_error(500, "Database path not configured.")
            return

        try:
            data = self.get_stats_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def get_stats_data(self) -> dict:
        db_resolved = Path(self.db_path).expanduser()
        # Ensure schema migrations and seed tables exist before raw summary reads.
        from mintry.core.wallet import MintryWallet
        wallet = MintryWallet(db_path=str(db_resolved))
        wallet.conn.close()
        conn = sqlite3.connect(db_resolved)
        try:
            # Total mandates
            total_mandates = conn.execute("SELECT COUNT(*) FROM mandates").fetchone()[0] or 0
            
            # Total budget
            total_budget = conn.execute("SELECT SUM(max_usd) FROM mandates").fetchone()[0] or 0.0
            
            # Total spent
            total_spent = conn.execute("SELECT SUM(spent_usd) FROM mandates").fetchone()[0] or 0.0
            
            # Mandates list
            mandates_rows = conn.execute(
                "SELECT id, max_usd, spent_usd, status, expires_at FROM mandates ORDER BY spent_usd DESC"
            ).fetchall()
            mandates = [
                {
                    "id": r[0],
                    "budget_usd": r[1],
                    "spent_usd": r[2],
                    "remaining_headroom": round((r[1] or 0.0) - (r[2] or 0.0), 4),
                    "status": r[3],
                    "expires_at": r[4] or "Never"
                }
                for r in mandates_rows
            ]
            
            # Top mandates
            top_rows = conn.execute(
                "SELECT id, spent_usd FROM mandates ORDER BY spent_usd DESC LIMIT 5"
            ).fetchall()
            top_mandates = [{"id": r[0], "spent_usd": r[1]} for r in top_rows]
            
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
            ]
            
            return {
                "stats": {
                    "total_mandates": total_mandates,
                    "total_budget": round(total_budget, 4),
                    "total_spent": round(total_spent, 4),
                    "remaining_headroom": round(total_budget - total_spent, 4)
                },
                "top_mandates": top_mandates,
                "mandates": mandates,
                "history": history
            }
        finally:
            conn.close()

def start_dashboard(db_path: str, host: str = "127.0.0.1", port: int = 8000):
    """Starts the local web server hosting the dashboard."""
    # Class-level assignment so the request handler knows which DB to query
    DashboardHandler.db_path = db_path
    DashboardHandler.dashboard_ui_origin = os.getenv(
        "MINTRY_DASHBOARD_UI_ORIGIN",
        DashboardHandler.dashboard_ui_origin,
    )
    
    server = ThreadedHTTPServer((host, port), DashboardHandler)
    print(f"✨ Mintry Observability Dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        server.server_close()
