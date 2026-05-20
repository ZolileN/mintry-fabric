import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional


class MintryWallet:
    def __init__(self, db_path="~/.mintry/vouchers.db"):
        self.path = Path(db_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep one connection open for the Logic Fabric
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self._init_db()

    def _init_db(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        # Ensure the table matches our 2026 spec: ID, Max, Spent, Status, Expires
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mandates (
                id TEXT PRIMARY KEY, 
                max_usd REAL, 
                spent_usd REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                expires_at TEXT DEFAULT NULL
            )
        """)

        # Add expires_at column if upgrading from an older schema
        try:
            self.conn.execute("ALTER TABLE mandates ADD COLUMN expires_at TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Create mandate_audit_log table for append-only audit trail
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mandate_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                mandate_id TEXT,
                action TEXT,
                amount REAL DEFAULT 0.0,
                details TEXT,
                FOREIGN KEY (mandate_id) REFERENCES mandates(id)
            )
        """)

        # Explicitly name the columns so we don't hit the 4-column vs 3-value error
        self.conn.execute("""
            INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status) 
            VALUES ('mt_task_882x', 0.01, 0.0, 'active')
        """)

        # Seed audit log for the default mandate if not present
        cursor = self.conn.execute("SELECT COUNT(*) FROM mandate_audit_log WHERE mandate_id = 'mt_task_882x'")
        if cursor.fetchone()[0] == 0:
            self._log_event("mt_task_882x", "create", 0.01, "Seed mandate initialized")

    def _log_event(self, mandate_id: str, action: str, amount: float = 0.0, details: str = None):
        """Helper to write to the mandate_audit_log table."""
        self.conn.execute(
            "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
            (mandate_id, action, float(amount), details)
        )

    def get_audit_log(self, mandate_id: str) -> list[dict]:
        """Fetch full append-only transaction history for a mandate."""
        cursor = self.conn.execute(
            "SELECT id, timestamp, action, amount, details FROM mandate_audit_log WHERE mandate_id = ? ORDER BY id ASC",
            (mandate_id,)
        )
        return [
            {"id": row[0], "timestamp": row[1], "action": row[2], "amount": row[3], "details": row[4]}
            for row in cursor.fetchall()
        ]

    def check_authorization(self, mandate_id, cost=0.002):
        row = self.conn.execute("SELECT max_usd, spent_usd FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
        if not row: return False
        if row[1] + cost > row[0]: return False
        
        self.conn.execute("UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?", (cost, mandate_id))
        self._log_event(mandate_id, "spend", cost, f"Authorized pre-flight base fee")
        return True

    def add_funds(self, mandate_id, amount: Decimal):
        """Increase the max_usd limit for a specific mandate."""
        try:
            # We increase the 'max_usd' allowing the 'spent_usd' to keep climbing
            self.conn.execute(
                "UPDATE mandates SET max_usd = max_usd + ? WHERE id = ?", 
                (float(amount), mandate_id)
            )
            self._log_event(mandate_id, "top_up", float(amount), f"Deposited ${float(amount):.4f} to increase limit")
            return True
        except Exception as e:
            print(f"Wallet deposit failed: {e}")
            return False

    def get_mandate(self, mandate_id):
        """Fetch mandate data from the SQLite database."""
        row = self.conn.execute(
            "SELECT max_usd, spent_usd, status, expires_at FROM mandates WHERE id = ?", 
            (mandate_id,)
        ).fetchone()
        
        if row:
            expires_at = None
            if row[3]:
                try:
                    expires_at = datetime.fromisoformat(row[3])
                except (ValueError, TypeError):
                    pass

            return {
                "budget_usd": row[0],
                "spent_usd": row[1],
                "status": row[2],
                "expires_at": expires_at,
            }
        
        return {"budget_usd": 0.0, "spent_usd": 0.0, "status": "unknown", "expires_at": None}

    def record_usage(self, mandate_id, actual_cost):
        """Adjusts the spent_usd based on actual token usage."""
        self.conn.execute(
            "UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?", 
            (float(actual_cost), mandate_id)
        )
        self._log_event(mandate_id, "spend", actual_cost, f"Metered actual LLM cost")

    def get_spent(self, mandate_id):
        row = self.conn.execute(
            "SELECT spent_usd FROM mandates WHERE id = ?", 
            (mandate_id,)
        ).fetchone()
        return row[0] if row else 0.0

    def create_mandate(self, mandate_id: str, max_usd: float, expires_at: Optional[datetime] = None):
        """Create a new mandate with the given budget ceiling and optional expiry."""
        expires_str = expires_at.isoformat() if expires_at else None
        self.conn.execute(
            "INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status, expires_at) VALUES (?, ?, 0.0, 'active', ?)",
            (mandate_id, float(max_usd), expires_str)
        )
        details = f"Created with budget ceiling ${max_usd:.4f}"
        if expires_str:
            details += f" and expiry {expires_str}"
        self._log_event(mandate_id, "create", max_usd, details)

    def exhaust_mandate(self, mandate_id: str):
        """Mark a mandate as exhausted, preventing further spend."""
        self.conn.execute(
            "UPDATE mandates SET status = 'exhausted' WHERE id = ?",
            (mandate_id,)
        )
        self._log_event(mandate_id, "exhaust", 0.0, "Mandate marked as exhausted")

    def is_expired(self, mandate_id: str) -> bool:
        """Check if a mandate has passed its expiry time."""
        mandate = self.get_mandate(mandate_id)
        if mandate["expires_at"] is None:
            return False
        now = datetime.now(timezone.utc)
        expires = mandate["expires_at"]
        # Ensure timezone-aware comparison
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        
        expired = now >= expires
        if expired and mandate.get("status") == "active":
            # Auto-update status to expired in the DB
            self.conn.execute("UPDATE mandates SET status = 'expired' WHERE id = ?", (mandate_id,))
            self._log_event(mandate_id, "expire", 0.0, f"Mandate automatically expired at {expires.isoformat()}")
            
        return expired

    def list_mandates(self) -> list[dict]:
        """List all mandates in the database."""
        cursor = self.conn.execute(
            "SELECT id, max_usd, spent_usd, status, expires_at FROM mandates ORDER BY id ASC"
        )
        return [
            {
                "id": row[0],
                "budget_usd": row[1],
                "spent_usd": row[2],
                "status": row[3],
                "expires_at": row[4],
            }
            for row in cursor.fetchall()
        ]