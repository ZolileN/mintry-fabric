import sqlite3
import threading
import queue
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from mintry.core.mandate_context import resolve_default_budget_usd, resolve_default_mandate_id
from mintry.core.opa import OPABundleEvaluator


class MintryWallet:
    _instances = {}
    _init_lock = threading.Lock()

    def __new__(cls, db_path="~/.mintry/vouchers.db"):
        path = Path(db_path).expanduser().resolve()
        with cls._init_lock:
            if path not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[path] = instance
            return cls._instances[path]

    def __init__(self, db_path="~/.mintry/vouchers.db"):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.path = Path(db_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

        # In-memory thread-safe cache for fast reading
        self._cache_lock = threading.Lock()
        self._spent_cache = {}    # mandate_id -> spent_usd (float)
        self._max_cache = {}      # mandate_id -> max_usd (float)
        self._status_cache = {}   # mandate_id -> status (str)
        self._expires_cache = {}  # mandate_id -> expires_at (datetime)
        self._reserved_cache = {}  # mandate_id -> reserved_usd (float)
        self._writer_failed = False

        # Queue for asynchronous persistence
        self._write_queue = queue.Queue()
        self._stop_writer = threading.Event()

        # Initialize the database schema using a temporary connection
        conn = sqlite3.connect(self.path, isolation_level=None)
        self._init_db_conn(conn)

        # Load existing mandates from DB to warm the cache
        cursor = conn.execute("SELECT id, max_usd, spent_usd, status, expires_at FROM mandates")
        for row in cursor.fetchall():
            m_id, max_u, spent_u, status, expires_str = row
            self._spent_cache[m_id] = spent_u
            self._max_cache[m_id] = max_u
            self._status_cache[m_id] = status
            self._expires_cache[m_id] = datetime.fromisoformat(expires_str) if expires_str else None
        conn.close()

        # Start the background writer thread
        self._bg_thread = threading.Thread(target=self._bg_writer, daemon=True)
        self._bg_thread.start()

        # OPA Evaluator (Phase 2)
        self._opa = OPABundleEvaluator()
        self.policy_cache = None  # Injected by __init__.py

    @property
    def conn(self):
        self.flush()
        # Fallback thread-local connection for tasks that need instant sync queries
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_db_conn(self, conn):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Ensure the table matches our 2026 spec: ID, Max, Spent, Status, Expires
        conn.execute("""
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
            conn.execute("ALTER TABLE mandates ADD COLUMN expires_at TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Create mandate_audit_log table for append-only audit trail
        conn.execute("""
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

        # Create policy_versions table for versioned policy records & rollback semantics
        # Stores all policy bundles received from the control plane (never mutated)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS policy_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER UNIQUE NOT NULL,
                policy_json TEXT NOT NULL,
                signature TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                issued_by TEXT DEFAULT 'control-plane',
                received_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                applied BOOLEAN DEFAULT 1,
                rollback_reason TEXT DEFAULT NULL,
                CONSTRAINT policy_versions_immutable UNIQUE (version, signature)
            )
        """)

        # Append-only record of proactive budget notices already delivered, so a
        # process restart does not re-notify a tenant about the same crossing.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                mandate_id TEXT NOT NULL,
                threshold REAL NOT NULL,
                budget_usd REAL NOT NULL,
                spent_usd REAL NOT NULL,
                projected_exhaustion_at TEXT DEFAULT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_notices_mandate
            ON budget_notices (mandate_id)
        """)

        default_id = resolve_default_mandate_id()
        default_budget = resolve_default_budget_usd()
        # Sane default mandate (agent id) — avoids silent $0.01 trap on unattributed traffic.
        conn.execute(
            """
            INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status)
            VALUES (?, ?, 0.0, 'active')
            """,
            (default_id, default_budget),
        )
        # Legacy seed id kept for backward compatibility with older docs/tests.
        conn.execute(
            """
            INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status)
            VALUES ('customer_support_agent', ?, 0.0, 'active')
            """,
            (default_budget,),
        )

        for seed_id, seed_budget in (
            (default_id, default_budget),
            ("customer_support_agent", default_budget),
        ):
            cursor = conn.execute(
                "SELECT COUNT(*) FROM mandate_audit_log WHERE mandate_id = ?",
                (seed_id,),
            )
            if cursor.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                    (seed_id, "create", seed_budget, "Default budget initialized"),
                )

    def _bg_writer(self):
        """Asynchronous DB writer that batches updates to avoid SQLite lock contention."""
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        while True:
            try:
                # Retrieve first work item
                item = self._write_queue.get(timeout=0.1)
                batch = [item]

                # Drain the queue to batch write up to 200 items in a single transaction
                while len(batch) < 200:
                    try:
                        batch.append(self._write_queue.get_nowait())
                    except queue.Empty:
                        break

                try:
                    with conn:
                        for action, args in batch:
                            if action == "record_usage":
                                mandate_id, actual_cost, ceiling = args
                                # A mandate can be authorized purely from a signed
                                # policy cap with no local row yet. Materialize the
                                # row so the spend lands somewhere durable instead
                                # of updating zero rows and vanishing on restart.
                                conn.execute(
                                    "INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status) VALUES (?, ?, 0.0, 'active')",
                                    (mandate_id, ceiling)
                                )
                                conn.execute(
                                    "UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?", 
                                    (actual_cost, mandate_id)
                                )
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "spend", actual_cost, "Metered actual LLM cost")
                                )
                            elif action == "create_mandate":
                                mandate_id, max_usd, expires_at = args
                                expires_str = expires_at.isoformat() if expires_at else None
                                conn.execute(
                                    "INSERT OR IGNORE INTO mandates (id, max_usd, spent_usd, status, expires_at) VALUES (?, ?, 0.0, 'active', ?)",
                                    (mandate_id, max_usd, expires_str)
                                )
                                details = f"Created with budget ceiling ${max_usd:.4f}"
                                if expires_str:
                                    details += f" and expiry {expires_str}"
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "create", max_usd, details)
                                )
                            elif action == "update_mandate":
                                mandate_id, max_usd, expires_at, status = args
                                expires_str = expires_at.isoformat() if expires_at else None
                                row = conn.execute("SELECT max_usd FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
                                old_max = row[0] if row else 0.0
                                conn.execute(
                                    "UPDATE mandates SET max_usd = ?, status = ?, expires_at = ? WHERE id = ?",
                                    (max_usd, status, expires_str, mandate_id)
                                )
                                details = f"Updated budget ceiling to ${max_usd:.4f} (was ${old_max:.4f}), status set to '{status}'"
                                if expires_str:
                                    details += f", expiry set to {expires_str}"
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "top_up", max_usd - old_max, details)
                                )
                            elif action == "exhaust_mandate":
                                mandate_id, = args
                                conn.execute(
                                    "UPDATE mandates SET max_usd = spent_usd, status = 'exhausted' WHERE id = ?",
                                    (mandate_id,)
                                )
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "exhaust", 0.0, "Mandate exhausted / revoked (budget reduced to match spend)")
                                )
                            elif action == "expire_mandate":
                                mandate_id, expires_str = args
                                conn.execute("UPDATE mandates SET status = 'expired' WHERE id = ?", (mandate_id,))
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "expire", 0.0, f"Mandate automatically expired at {expires_str}")
                                )
                            elif action == "add_funds":
                                mandate_id, amount = args
                                conn.execute(
                                    "UPDATE mandates SET max_usd = max_usd + ? WHERE id = ?", 
                                    (amount, mandate_id)
                                )
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, "top_up", amount, f"Deposited ${amount:.4f} to increase limit")
                                )
                            elif action == "log_decision":
                                mandate_id, decision_action, amount, details = args
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (mandate_id, decision_action, amount, details)
                                )
                            elif action == "record_budget_notice":
                                (
                                    mandate_id,
                                    threshold,
                                    budget_usd,
                                    spent_usd,
                                    projected_exhaustion_at,
                                ) = args
                                conn.execute(
                                    "INSERT INTO budget_notices (mandate_id, threshold, budget_usd, spent_usd, projected_exhaustion_at) VALUES (?, ?, ?, ?, ?)",
                                    (mandate_id, threshold, budget_usd, spent_usd, projected_exhaustion_at)
                                )
                                conn.execute(
                                    "INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)",
                                    (
                                        mandate_id,
                                        "notice",
                                        spent_usd,
                                        f"Budget notice sent at {threshold * 100:.0f}% of ${budget_usd:.4f}",
                                    )
                                )
                except Exception as e:
                    print(f"[BG_WRITER_ERROR] {e}")
                    self._writer_failed = True
                    # Re-queue failed batch so flush()/retry can recover
                    for item in batch:
                        self._write_queue.put(item)
                finally:
                    # Always mark tasks as done to prevent queue.join() deadlocks
                    for _ in range(len(batch)):
                        self._write_queue.task_done()

            except queue.Empty:
                if self._stop_writer.is_set() and self._write_queue.empty():
                    break
                continue
        conn.close()

    def get_audit_log(self, mandate_id: str) -> list[dict]:
        """Fetch full append-only transaction history for a mandate directly from DB."""
        self.flush()
        conn = sqlite3.connect(self.path, isolation_level=None)
        cursor = conn.execute(
            "SELECT id, timestamp, action, amount, details FROM mandate_audit_log WHERE mandate_id = ? ORDER BY id ASC",
            (mandate_id,)
        )
        logs = [
            {"id": row[0], "timestamp": row[1], "action": row[2], "amount": row[3], "details": row[4]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return logs

    def check_authorization(self, mandate_id, cost=0.002):
        """Pre-flight authorization check: uses cache for sub-millisecond lookups."""
        mandate = self.get_mandate(mandate_id)
        if mandate["status"] == "unknown":
            return False

        # Phase 2 E4: use already-materialized flat rules only (no OPA CLI).
        if self._opa and self.policy_cache:
            active_policy = self.policy_cache.get_active_policy()
            if active_policy:
                self._opa.set_bundle_data(
                    getattr(self.policy_cache, "_flat_rules", None) or active_policy.mandates
                )
                opa_result = self._opa.evaluate(
                    f"data.mintry.mandate.{mandate_id}", {"cost": cost}
                )
                if opa_result is not None:
                    if isinstance(opa_result, dict) and "max_usd" in opa_result:
                        mandate["budget_usd"] = float(opa_result["max_usd"])
                    elif opa_result is False:
                        self.log_decision(mandate_id, "block", cost, "Blocked by OPA policy")
                        return False

        if mandate["spent_usd"] + cost > mandate["budget_usd"]:
            self.log_decision(mandate_id, "block", cost, f"Blocked: exceeds budget")
            return False

        self.record_usage(mandate_id, cost)
        return True

    def add_funds(self, mandate_id, amount: Decimal):
        """Increase the max_usd limit for a specific mandate."""
        try:
            with self._cache_lock:
                if mandate_id in self._max_cache:
                    self._max_cache[mandate_id] += float(amount)
                else:
                    self._max_cache[mandate_id] = float(amount)
            
            self._write_queue.put(("add_funds", (mandate_id, float(amount))))
            return True
        except Exception as e:
            print(f"Wallet deposit failed: {e}")
            return False

    def get_mandate(self, mandate_id):
        """Fetch mandate data from cache, falling back to DB if missing."""
        with self._cache_lock:
            if mandate_id in self._spent_cache:
                return {
                    "budget_usd": self._max_cache[mandate_id],
                    "spent_usd": self._spent_cache[mandate_id],
                    "status": self._status_cache[mandate_id],
                    "expires_at": self._expires_cache[mandate_id],
                }

        # Cache miss (e.g. newly created mandate not loaded yet)
        conn = sqlite3.connect(self.path, isolation_level=None)
        row = conn.execute(
            "SELECT max_usd, spent_usd, status, expires_at FROM mandates WHERE id = ?", 
            (mandate_id,)
        ).fetchone()
        conn.close()

        if row:
            max_u, spent_u, status, expires_str = row
            expires_at = datetime.fromisoformat(expires_str) if expires_str else None
            with self._cache_lock:
                self._max_cache[mandate_id] = max_u
                self._spent_cache[mandate_id] = spent_u
                self._status_cache[mandate_id] = status
                self._expires_cache[mandate_id] = expires_at
            return {
                "budget_usd": max_u,
                "spent_usd": spent_u,
                "status": status,
                "expires_at": expires_at,
            }

        return {"budget_usd": 0.0, "spent_usd": 0.0, "status": "unknown", "expires_at": None}

    def record_usage(self, mandate_id, actual_cost):
        """Adjusts the spent_usd in cache and queues the DB update.

        Settles any pre-flight reservation for this mandate (default $0.01).
        """
        cost = float(actual_cost)
        with self._cache_lock:
            reserved = float(self._reserved_cache.get(mandate_id, 0.0) or 0.0)
            release = min(reserved, 0.01)
            self._reserved_cache[mandate_id] = max(0.0, reserved - release)
            if mandate_id in self._spent_cache:
                self._spent_cache[mandate_id] += cost
            else:
                self._spent_cache[mandate_id] = cost
            ceiling = float(self._max_cache.get(mandate_id, 0.0) or 0.0)

        self._write_queue.put(("record_usage", (mandate_id, cost, ceiling)))

    def try_reserve(self, mandate_id: str, amount: float, budget_usd: float) -> bool:
        """Atomically reserve headroom against spent+reserved for concurrent safety."""
        amount = float(amount)
        budget_usd = float(budget_usd)
        with self._cache_lock:
            spent = float(self._spent_cache.get(mandate_id, 0.0) or 0.0)
            reserved = float(self._reserved_cache.get(mandate_id, 0.0) or 0.0)
            if spent + reserved + amount > budget_usd + 1e-9:
                return False
            self._reserved_cache[mandate_id] = reserved + amount
            return True

    def release_reservation(self, mandate_id: str, amount: float = 0.01) -> None:
        """Release unused pre-flight reservation (e.g. upstream failure)."""
        amount = float(amount)
        with self._cache_lock:
            reserved = float(self._reserved_cache.get(mandate_id, 0.0) or 0.0)
            self._reserved_cache[mandate_id] = max(0.0, reserved - amount)

    def log_decision(self, mandate_id: str, action: str, amount: float = 0.0, details: str = ""):
        """Append an enforcement decision (allow/block/throttle) to the audit log."""
        self._write_queue.put(("log_decision", (mandate_id, action, float(amount), details)))

    def record_budget_notice(
        self,
        mandate_id: str,
        threshold: float,
        budget_usd: float,
        spent_usd: float,
        projected_exhaustion_at: Optional[str] = None,
    ) -> None:
        """Append a delivered budget notice. Never mutates an existing row."""
        self._write_queue.put((
            "record_budget_notice",
            (
                mandate_id,
                float(threshold),
                float(budget_usd),
                float(spent_usd),
                projected_exhaustion_at,
            ),
        ))

    def delivered_budget_notices(self) -> list[tuple[str, float, float]]:
        """Return ``(mandate_id, threshold, budget_usd)`` for every notice sent."""
        self.flush()
        conn = sqlite3.connect(self.path, isolation_level=None)
        try:
            rows = conn.execute(
                "SELECT mandate_id, threshold, budget_usd FROM budget_notices"
            ).fetchall()
        finally:
            conn.close()
        return [(r[0], float(r[1]), float(r[2])) for r in rows]

    def list_budget_notices(self, limit: int = 25) -> list[dict]:
        """Most recent budget notices, newest first (for dashboard surfaces)."""
        self.flush()
        conn = sqlite3.connect(self.path, isolation_level=None)
        try:
            rows = conn.execute(
                "SELECT timestamp, mandate_id, threshold, budget_usd, spent_usd, "
                "projected_exhaustion_at FROM budget_notices ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "timestamp": r[0],
                "mandate_id": r[1],
                "threshold": float(r[2]),
                "budget_usd": float(r[3]),
                "spent_usd": float(r[4]),
                "projected_exhaustion_at": r[5],
            }
            for r in rows
        ]

    def spend_in_window(self, mandate_id: str, hours: float) -> float:
        """Total metered spend for a mandate over the trailing ``hours``.

        Used only by the analytics/forecast layer, never by the enforcement path.
        """
        self.flush()
        # Match the millisecond precision SQLite writes, so the window boundary
        # does not silently widen by up to a second.
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=float(hours))
        ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        conn = sqlite3.connect(self.path, isolation_level=None)
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) FROM mandate_audit_log "
                "WHERE mandate_id = ? AND action = 'spend' AND timestamp >= ?",
                (mandate_id, cutoff),
            ).fetchone()
        finally:
            conn.close()
        return float(row[0] or 0.0) if row else 0.0

    def get_spent(self, mandate_id):
        """Retrieve spent amount from cache."""
        with self._cache_lock:
            return self._spent_cache.get(mandate_id, 0.0)

    def create_mandate(self, mandate_id: str, max_usd: float, expires_at: Optional[datetime] = None):
        """Create a new mandate, updating cache first then queueing DB write."""
        with self._cache_lock:
            self._max_cache[mandate_id] = float(max_usd)
            self._spent_cache[mandate_id] = 0.0
            self._status_cache[mandate_id] = "active"
            self._expires_cache[mandate_id] = expires_at
            self._reserved_cache[mandate_id] = 0.0

        self._write_queue.put(("create_mandate", (mandate_id, float(max_usd), expires_at)))

    def update_mandate(self, mandate_id: str, max_usd: float, expires_at: Optional[datetime] = None, status: str = "active"):
        """Update an existing mandate, updating cache first then queueing DB write."""
        with self._cache_lock:
            self._max_cache[mandate_id] = float(max_usd)
            self._status_cache[mandate_id] = status
            self._expires_cache[mandate_id] = expires_at

        self._write_queue.put(("update_mandate", (mandate_id, float(max_usd), expires_at, status)))

    def exhaust_mandate(self, mandate_id: str):
        """Mark a mandate as exhausted in cache and queue DB write."""
        with self._cache_lock:
            self._status_cache[mandate_id] = "exhausted"

        self._write_queue.put(("exhaust_mandate", (mandate_id,)))

    def is_expired(self, mandate_id: str) -> bool:
        """Check if a mandate has passed its expiry time using cache."""
        mandate = self.get_mandate(mandate_id)
        if mandate["expires_at"] is None:
            return False
        
        now = datetime.now(timezone.utc)
        expires = mandate["expires_at"]
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        expired = now >= expires
        if expired and mandate["status"] == "active":
            with self._cache_lock:
                self._status_cache[mandate_id] = "expired"
            self._write_queue.put(("expire_mandate", (mandate_id, expires.isoformat())))

        return expired

    def list_mandates(self) -> list[dict]:
        """List all mandates directly from the database (called by dashboard)."""
        self.flush()
        conn = sqlite3.connect(self.path, isolation_level=None)
        cursor = conn.execute(
            "SELECT id, max_usd, spent_usd, status, expires_at FROM mandates ORDER BY id ASC"
        )
        results = []
        for row in cursor.fetchall():
            expires_val = None
            if row[4]:
                try:
                    expires_val = datetime.fromisoformat(row[4])
                except (ValueError, TypeError):
                    pass
            results.append({
                "id": row[0],
                "budget_usd": row[1],
                "spent_usd": row[2],
                "status": row[3],
                "expires_at": expires_val,
            })
        conn.close()
        return results

    def flush(self):
        """Block until all pending database writes are completed."""
        self._write_queue.join()

    def close(self):
        """Flush pending writes and stop the background writer."""
        self.flush()
        self._stop_writer.set()
        if getattr(self, "_bg_thread", None):
            self._bg_thread.join(timeout=5)