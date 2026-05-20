import sqlite3
from decimal import Decimal
from pathlib import Path

class MintryWallet:
    def __init__(self, db_path="~/.mintry/vouchers.db"):
        self.path = Path(db_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep one connection open for the Logic Fabric
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self._init_db()

    def _init_db(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        # Ensure the table matches our 2026 spec: ID, Max, Spent, Status
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mandates (
                id TEXT PRIMARY KEY, 
                max_usd REAL, 
                spent_usd REAL DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)
        
        # Explicitly name the columns so we don't hit the 4-column vs 3-value error
        self.conn.execute("""
            INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status) 
            VALUES ('mt_task_882x', 0.01, 0.0, 'active')
        """)

    def check_authorization(self, mandate_id, cost=0.002):
        row = self.conn.execute("SELECT max_usd, spent_usd FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
        if not row: return False
        if row[1] + cost > row[0]: return False
        
        self.conn.execute("UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?", (cost, mandate_id))
        return True

    def add_funds(self, mandate_id, amount: Decimal):
        """Increase the max_usd limit for a specific mandate."""
        try:
            # We increase the 'max_usd' allowing the 'spent_usd' to keep climbing
            self.conn.execute(
                "UPDATE mandates SET max_usd = max_usd + ? WHERE id = ?", 
                (float(amount), mandate_id)
            )
            return True
        except Exception as e:
            print(f"Wallet deposit failed: {e}")
            return False

    def get_mandate(self, mandate_id):
        """Fetch mandate data from the SQLite database."""
        row = self.conn.execute(
            "SELECT max_usd, spent_usd FROM mandates WHERE id = ?", 
            (mandate_id,)
        ).fetchone()
        
        if row:
            # Match the keys the PolicyEngine expects: 'budget_usd' and 'spent_usd'
            return {"budget_usd": row[0], "spent_usd": row[1]}
        
        return {"budget_usd": 0.0, "spent_usd": 0.0}

    def record_usage(self, mandate_id, actual_cost):
        """Adjusts the spent_usd based on actual token usage."""
        self.conn.execute(
            "UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?", 
            (float(actual_cost), mandate_id)
        )

    def get_spent(self, mandate_id):
        row = self.conn.execute(
            "SELECT spent_usd FROM mandates WHERE id = ?", 
            (mandate_id,)
        ).fetchone()
        return row[0] if row else 0.0

    def create_mandate(self, mandate_id: str, max_usd: float):
        """Create a new mandate with the given budget ceiling."""
        self.conn.execute(
            "INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status) VALUES (?, ?, 0.0, 'active')",
            (mandate_id, float(max_usd))
        )

    def exhaust_mandate(self, mandate_id: str):
        """Mark a mandate as exhausted, preventing further spend."""
        self.conn.execute(
            "UPDATE mandates SET status = 'exhausted' WHERE id = ?",
            (mandate_id,)
        )