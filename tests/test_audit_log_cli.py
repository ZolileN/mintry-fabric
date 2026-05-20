"""Tests for Mandate Audit Log and CLI commands."""

import pytest
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from mintry.core.wallet import MintryWallet
from mintry.cli import main


@pytest.fixture
def temp_db(tmp_path):
    """Fixture to provide a clean, isolated database path."""
    return str(tmp_path / "test_vouchers.db")


# ── Audit Log Tests ──────────────────────────────────────────────────

def test_wallet_logs_create_and_top_up(temp_db):
    """Wallet correctly logs mandate creation and deposits."""
    wallet = MintryWallet(db_path=temp_db)
    
    # 1. Create mandate
    wallet.create_mandate("test_audit_01", 10.0)
    
    logs = wallet.get_audit_log("test_audit_01")
    assert len(logs) == 1
    assert logs[0]["action"] == "create"
    assert logs[0]["amount"] == 10.0
    assert "Created with budget ceiling" in logs[0]["details"]

    # 2. Add funds
    wallet.add_funds("test_audit_01", Decimal("5.50"))
    
    logs = wallet.get_audit_log("test_audit_01")
    assert len(logs) == 2
    assert logs[1]["action"] == "top_up"
    assert logs[1]["amount"] == 5.50
    assert "Deposited $5.5000" in logs[1]["details"]


def test_wallet_logs_spend_and_exhaust(temp_db):
    """Wallet correctly logs spend events and mandate exhaustion."""
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("test_audit_02", 1.00)

    # 1. Record usage
    wallet.record_usage("test_audit_02", 0.15)
    
    logs = wallet.get_audit_log("test_audit_02")
    assert len(logs) == 2  # create, spend
    assert logs[1]["action"] == "spend"
    assert logs[1]["amount"] == 0.15
    assert "Metered actual LLM cost" in logs[1]["details"]

    # 2. Exhaust
    wallet.exhaust_mandate("test_audit_02")
    
    logs = wallet.get_audit_log("test_audit_02")
    assert len(logs) == 3
    assert logs[2]["action"] == "exhaust"
    assert logs[2]["amount"] == 0.0
    assert "exhausted" in logs[2]["details"]


def test_wallet_logs_expiration(temp_db):
    """Wallet logs when a mandate automatically expires during is_expired checks."""
    wallet = MintryWallet(db_path=temp_db)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    wallet.create_mandate("expired_test", 5.0, expires_at=past)

    # Trigger expiration check
    assert wallet.is_expired("expired_test") is True

    logs = wallet.get_audit_log("expired_test")
    # Should have create, then expire log
    assert len(logs) == 2
    assert logs[1]["action"] == "expire"
    assert "automatically expired" in logs[1]["details"]


# ── CLI Commands Tests ───────────────────────────────────────────────

def test_cli_list_mandates(temp_db, capsys):
    """CLI mandates list prints all mandates in an ASCII table."""
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("cli_task_a", 10.0)
    wallet.create_mandate("cli_task_b", 5.0)
    wallet.conn.close()

    sys.argv = ["mintry", "--db", temp_db, "mandates", "list"]
    main()

    captured = capsys.readouterr()
    stdout = captured.out

    assert "cli_task_a" in stdout
    assert "cli_task_b" in stdout
    assert "active" in stdout
    assert "$10.0000" in stdout
    assert "$5.0000" in stdout


def test_cli_inspect_mandate(temp_db, capsys):
    """CLI mandates inspect prints details and audit timeline."""
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("inspect_me", 20.0)
    wallet.add_funds("inspect_me", Decimal("10.0"))
    wallet.conn.close()

    sys.argv = ["mintry", "--db", temp_db, "mandates", "inspect", "inspect_me"]
    main()

    captured = capsys.readouterr()
    stdout = captured.out

    assert "Mandate ID: inspect_me" in stdout
    assert "Budget:     $30.0000" in stdout
    assert "History/Audit Log:" in stdout
    assert "create" in stdout
    assert "top_up" in stdout
    assert "$20.0000" in stdout
    assert "$10.0000" in stdout


def test_cli_inspect_nonexistent_mandate(temp_db, capsys):
    """CLI mandates inspect exits with status code 1 for non-existent mandates."""
    # Ensure database is initialized
    wallet = MintryWallet(db_path=temp_db)
    wallet.conn.close()

    sys.argv = ["mintry", "--db", temp_db, "mandates", "inspect", "does_not_exist"]
    
    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    
    captured = capsys.readouterr()
    assert "Error: Mandate 'does_not_exist' not found." in captured.err


def test_cli_list_mandates_accepts_db_after_subcommand(temp_db, capsys):
    """CLI accepts --db after the mandates subcommand."""
    wallet = MintryWallet(db_path=temp_db)
    wallet.create_mandate("cli_task_c", 7.5)
    wallet.conn.close()

    sys.argv = ["mintry", "mandates", "--db", temp_db, "list"]
    main()

    captured = capsys.readouterr()
    assert "cli_task_c" in captured.out


def test_cli_dashboard_accepts_db_after_subcommand(temp_db, monkeypatch):
    """CLI accepts --db after the dashboard subcommand."""
    captured = {}

    def fake_start_dashboard(db_path: str, host: str = "127.0.0.1", port: int = 8000):
        captured["db_path"] = db_path
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("mintry.core.dashboard.start_dashboard", fake_start_dashboard)

    sys.argv = ["mintry", "dashboard", "--db", temp_db, "--host", "127.0.0.1", "--port", "8001"]
    main()

    assert captured == {
        "db_path": temp_db,
        "host": "127.0.0.1",
        "port": 8001,
    }
