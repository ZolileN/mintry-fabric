#!/usr/bin/env python3
"""Seed a demo SQLite ledger with plausible agent names and audit history.

Usage:
    uv run python scripts/seed_demo_environment.py [--db test_data/demo.db]
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEMO_AGENTS = [
    {
        "id": "customer_support_agent",
        "max_usd": 50.0,
        "spent_usd": 22.10,
        "status": "active",
    },
    {
        "id": "research_agent",
        "max_usd": 250.0,
        "spent_usd": 187.45,
        "status": "active",
    },
    {
        "id": "pricing_agent",
        "max_usd": 75.0,
        "spent_usd": 8.20,
        "status": "active",
    },
    {
        "id": "escalation_agent",
        "max_usd": 30.0,
        "spent_usd": 29.98,
        "status": "exhausted",
    },
]

AUDIT_EVENTS = [
    ("customer_support_agent", "allow", 0.0, "Request authorized — ticket classification"),
    ("customer_support_agent", "spend", 0.0042, "Metered actual LLM cost"),
    ("customer_support_agent", "allow", 0.0, "Request authorized — response draft"),
    ("customer_support_agent", "spend", 0.0068, "Metered actual LLM cost"),
    ("research_agent", "allow", 0.0, "Request authorized — literature scan"),
    ("research_agent", "spend", 0.0312, "Metered actual LLM cost"),
    ("research_agent", "block", 0.0, "Budget threshold warning — request rejected"),
    ("pricing_agent", "allow", 0.0, "Request authorized — competitor analysis"),
    ("pricing_agent", "spend", 0.0021, "Metered actual LLM cost"),
    ("escalation_agent", "block", 0.0, "Budget exhausted ($29.9800 / $30.0000)"),
    ("escalation_agent", "exhaust", 0.0, "Mandate marked as exhausted"),
    ("research_agent", "top_up", 50.0, "Updated budget ceiling to $250.0000 (was $200.0000), status set to 'active'"),
    ("customer_support_agent", "create", 50.0, "Created with budget ceiling $50.0000"),
    ("research_agent", "create", 200.0, "Created with budget ceiling $200.0000"),
    ("pricing_agent", "create", 75.0, "Created with budget ceiling $75.0000"),
]


def _is_test_mandate(mandate_id: str) -> bool:
    """Return True if mandate_id looks like integration-test leakage."""
    lowered = mandate_id.lower()
    if lowered.startswith("kill_switch_"):
        return True
    if lowered in ("smoke_task", "new-agent", "test agent", "mt_task_882x"):
        return True
    if "test" in lowered and "agent" in lowered:
        return True
    return False


def is_test_mandate(mandate_id: str) -> bool:
    """Public helper — filter integration-test mandates from dashboard views."""
    return _is_test_mandate(mandate_id)


def seed_demo_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mandates (
            id TEXT PRIMARY KEY,
            max_usd REAL,
            spent_usd REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            expires_at TEXT DEFAULT NULL
        )
    """)
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

    conn.execute("DELETE FROM mandate_audit_log")
    conn.execute("DELETE FROM mandates")

    now = datetime.now(timezone.utc)
    for agent in DEMO_AGENTS:
        conn.execute(
            "INSERT INTO mandates (id, max_usd, spent_usd, status, expires_at) VALUES (?, ?, ?, ?, NULL)",
            (agent["id"], agent["max_usd"], agent["spent_usd"], agent["status"]),
        )

    for i, (mandate_id, action, amount, details) in enumerate(AUDIT_EVENTS):
        ts = (now - timedelta(minutes=len(AUDIT_EVENTS) - i)).isoformat().replace("+00:00", "Z")
        conn.execute(
            "INSERT INTO mandate_audit_log (timestamp, mandate_id, action, amount, details) VALUES (?, ?, ?, ?, ?)",
            (ts, mandate_id, action, amount, details),
        )

    conn.close()
    print(f"Demo environment seeded at {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mintry demo ledger")
    parser.add_argument(
        "--db",
        default="test_data/demo.db",
        help="Path to SQLite database (default: test_data/demo.db)",
    )
    args = parser.parse_args()
    seed_demo_db(Path(args.db))


if __name__ == "__main__":
    main()
