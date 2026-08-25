"""Proactive budget notices and zero-touch agent enrollment."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from mintry.core.attention import build_attention
from mintry.core.engine import PolicyEngine
from mintry.core.notifications import (
    BudgetWatch,
    DEFAULT_THRESHOLDS,
    parse_thresholds,
    project_exhaustion,
)
from mintry.core.wallet import MintryWallet


@pytest.fixture
def wallet(tmp_path):
    return MintryWallet(db_path=str(tmp_path / "notices.db"))


# ── Threshold parsing ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("50,80,95", (0.5, 0.8, 0.95)),
        ("0.5,0.8,0.95", (0.5, 0.8, 0.95)),
        ("90", (0.9,)),
        ("  75 , 90  ", (0.75, 0.9)),
        # Malformed input degrades to the default instead of breaking startup.
        ("", DEFAULT_THRESHOLDS),
        (None, DEFAULT_THRESHOLDS),
        ("abc", DEFAULT_THRESHOLDS),
        ("0,-5,200", DEFAULT_THRESHOLDS),
    ],
)
def test_parse_thresholds(raw, expected):
    assert parse_thresholds(raw) == expected


# ── Crossing detection ───────────────────────────────────────────────

def test_notice_fires_once_per_threshold(wallet):
    sent = []
    watch = BudgetWatch(wallet, thresholds=[0.5, 0.8], dispatch=sent.append)
    wallet.create_mandate("agent", 100.0)

    wallet.record_usage("agent", 55.0)
    assert len(watch.evaluate("agent", budget_usd=100.0)) == 1
    assert sent[-1]["threshold"] == 0.5

    # Still above 50% but below 80% — nothing new to say.
    wallet.record_usage("agent", 5.0)
    assert watch.evaluate("agent", budget_usd=100.0) == []

    wallet.record_usage("agent", 25.0)
    notices = watch.evaluate("agent", budget_usd=100.0)
    assert len(notices) == 1
    assert notices[0].threshold == 0.8
    assert len(sent) == 2


def test_single_large_charge_sends_one_notice_not_three(wallet):
    sent = []
    watch = BudgetWatch(wallet, thresholds=[0.5, 0.8, 0.95], dispatch=sent.append)
    wallet.create_mandate("agent", 10.0)

    wallet.record_usage("agent", 9.9)
    notices = watch.evaluate("agent", budget_usd=10.0)

    assert len(notices) == 1
    assert notices[0].threshold == 0.95
    assert len(sent) == 1

    # Every skipped threshold is still marked delivered, so nothing backfills later.
    assert watch.evaluate("agent", budget_usd=10.0) == []


def test_raising_the_cap_rearms_thresholds(wallet):
    watch = BudgetWatch(wallet, thresholds=[0.8])
    wallet.create_mandate("agent", 10.0)
    wallet.record_usage("agent", 8.5)

    assert len(watch.evaluate("agent", budget_usd=10.0)) == 1
    assert watch.evaluate("agent", budget_usd=10.0) == []
    # A top-up to $10.50 puts spend back at 81% of a new ceiling: warn again.
    assert len(watch.evaluate("agent", budget_usd=10.5)) == 1


def test_notices_survive_a_restart(wallet, tmp_path):
    db = str(tmp_path / "notices.db")
    watch = BudgetWatch(wallet, thresholds=[0.8])
    wallet.create_mandate("agent", 20.0)
    wallet.record_usage("agent", 17.0)
    assert len(watch.evaluate("agent", budget_usd=20.0)) == 1
    wallet.flush()

    # A fresh watch over the same ledger must not re-alert the tenant.
    revived = BudgetWatch(MintryWallet(db_path=db), thresholds=[0.8])
    assert revived.evaluate("agent", budget_usd=20.0) == []


def test_zero_budget_never_notices(wallet):
    watch = BudgetWatch(wallet, thresholds=[0.5])
    assert watch.observe("agent", 5.0, 0.0) == []


def test_notice_is_recorded_append_only(wallet):
    watch = BudgetWatch(wallet, thresholds=[0.5])
    wallet.create_mandate("agent", 40.0)
    wallet.record_usage("agent", 30.0)
    watch.evaluate("agent", budget_usd=40.0)
    wallet.flush()

    recorded = wallet.list_budget_notices()
    assert len(recorded) == 1
    assert recorded[0]["mandate_id"] == "agent"
    assert recorded[0]["threshold"] == 0.5

    watch.evaluate("agent", budget_usd=40.0)
    wallet.flush()
    assert len(wallet.list_budget_notices()) == 1


def test_notice_payload_reads_like_a_sentence(wallet):
    watch = BudgetWatch(wallet, thresholds=[0.8])
    wallet.create_mandate("nightly_summarizer", 250.0)
    wallet.record_usage("nightly_summarizer", 210.0)

    payload = watch.evaluate("nightly_summarizer", budget_usd=250.0)[0].to_payload()
    assert payload["event"] == "budget_threshold_crossed"
    assert payload["headline"] == (
        "nightly_summarizer has used 84% of its $250.00 budget"
    )
    assert payload["remaining_usd"] == pytest.approx(40.0)


# ── Forecast ─────────────────────────────────────────────────────────

def test_projection_needs_a_measurable_burn_rate():
    assert project_exhaustion(10.0, None) is None
    assert project_exhaustion(10.0, 0.0) is None
    # An effectively idle agent gets no invented date rather than one centuries out.
    assert project_exhaustion(10.0, 0.0000001) is None


def test_projection_extrapolates_the_observed_rate():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    projected = project_exhaustion(10.0, 2.0, now=now)
    assert projected == (now + timedelta(hours=5)).isoformat()


def test_burn_rate_comes_from_the_trailing_window(wallet):
    wallet.create_mandate("agent", 100.0)
    wallet.record_usage("agent", 12.0)
    wallet.flush()

    stale = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    conn = sqlite3.connect(wallet.path)
    with conn:
        conn.execute(
            "INSERT INTO mandate_audit_log (timestamp, mandate_id, action, amount, details) "
            "VALUES (?, 'agent', 'spend', 500.0, 'last week')",
            (stale,),
        )
    conn.close()

    # Only the recent charge counts toward the burn rate.
    assert wallet.spend_in_window("agent", 6.0) == pytest.approx(12.0)
    assert wallet.spend_in_window("agent", 24.0) == pytest.approx(512.0)


# ── Auto-enrollment ──────────────────────────────────────────────────

def test_unknown_agent_is_blocked_without_a_default_cap(wallet):
    engine = PolicyEngine(wallet)
    assert engine.default_cap() is None
    assert engine.authorize("never_seen", None, deduct=False) is False


def test_unknown_agent_is_enrolled_at_the_default_cap(wallet):
    sent = []
    engine = PolicyEngine(wallet, default_mandate_usd=25.0)
    engine._dispatch_webhook = sent.append

    assert engine.authorize("brand_new", None, deduct=False) is True

    mandate = wallet.get_mandate("brand_new")
    assert mandate["status"] == "active"
    assert mandate["budget_usd"] == pytest.approx(25.0)
    assert sent[-1]["event"] == "mandate_auto_enrolled"
    assert sent[-1]["budget_usd"] == pytest.approx(25.0)


def test_default_cap_reads_the_environment(wallet, monkeypatch):
    monkeypatch.setenv("MINTRY_DEFAULT_MANDATE_USD", "12.50")
    assert PolicyEngine(wallet).default_cap() == pytest.approx(12.5)

    monkeypatch.setenv("MINTRY_DEFAULT_MANDATE_USD", "not-a-number")
    assert PolicyEngine(wallet).default_cap() is None

    monkeypatch.setenv("MINTRY_DEFAULT_MANDATE_USD", "0")
    assert PolicyEngine(wallet).default_cap() is None


def test_signed_default_rule_overrides_the_local_value(wallet):
    class StubCache:
        def mandate_rule(self, mandate_id):
            if mandate_id == "__default__":
                return {"max_usd": 40.0}
            return None

    engine = PolicyEngine(wallet, default_mandate_usd=5.0)
    engine.policy_cache = StubCache()
    assert engine.default_cap() == pytest.approx(40.0)


def test_centrally_budgeted_agent_gets_a_local_row(wallet, tmp_path):
    """A signed cap must materialize a ledger row so spend has somewhere to land."""

    class StubCache:
        def mandate_rule(self, mandate_id):
            if mandate_id == "policy_agent":
                return {"max_usd": 75.0, "allow": True}
            return None

    engine = PolicyEngine(wallet)
    engine.policy_cache = StubCache()

    assert engine.authorize("policy_agent", None, deduct=False) is True
    wallet.flush()

    row = sqlite3.connect(wallet.path).execute(
        "SELECT max_usd, status FROM mandates WHERE id = 'policy_agent'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(75.0)
    assert row[1] == "active"


def test_metered_spend_is_never_silently_dropped(wallet):
    """Spend for a mandate with no ledger row used to update zero rows."""
    wallet.record_usage("ghost_agent", 3.25)
    wallet.flush()

    row = sqlite3.connect(wallet.path).execute(
        "SELECT spent_usd FROM mandates WHERE id = 'ghost_agent'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(3.25)


# ── Attention feed ───────────────────────────────────────────────────

def test_attention_is_clear_when_everything_is_fine():
    result = build_attention([
        {"id": "a", "budget_usd": 100.0, "spent_usd": 10.0, "status": "active"},
        {"id": "b", "budget_usd": 100.0, "spent_usd": 20.0, "status": "active"},
    ])
    assert result["status"] == "ok"
    assert result["headline"] == "All 2 agents are within budget"
    assert result["items"] == []


def test_attention_flags_blocked_agents_first():
    result = build_attention([
        {"id": "warn", "budget_usd": 100.0, "spent_usd": 85.0, "status": "active"},
        {"id": "blocked", "budget_usd": 50.0, "spent_usd": 50.0, "status": "exhausted"},
    ])
    assert result["status"] == "action_required"
    assert result["critical_count"] == 1
    assert result["items"][0]["mandate_id"] == "blocked"
    assert result["items"][0]["severity"] == "critical"
    assert result["items"][1]["severity"] == "warning"


def test_attention_warns_before_anything_is_blocked():
    result = build_attention([
        {"id": "warm", "budget_usd": 100.0, "spent_usd": 82.0, "status": "active"},
    ])
    assert result["status"] == "watch"
    assert "approaching its budget" in result["headline"]
    assert result["items"][0]["suggested_action"] == "raise_budget"


def test_attention_surfaces_imminent_expiry():
    soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    result = build_attention([
        {"id": "temp", "budget_usd": 100.0, "spent_usd": 1.0, "status": "active", "expires_at": soon},
    ])
    assert any(i["suggested_action"] == "extend_expiry" for i in result["items"])


def test_attention_suggests_reclaiming_idle_budget():
    result = build_attention([
        {"id": "idle", "budget_usd": 500.0, "spent_usd": 0.0, "status": "active"},
    ])
    assert result["status"] == "ok"  # informational only, nothing is at risk
    assert result["items"][0]["severity"] == "info"
    assert result["items"][0]["suggested_action"] == "reclaim_budget"


def test_attention_reports_broken_policy_delivery():
    result = build_attention(
        [{"id": "a", "budget_usd": 100.0, "spent_usd": 1.0, "status": "active"}],
        policy_sync={"last_sync_error": "connection refused", "last_synced_at": None},
    )
    platform = [i for i in result["items"] if i["mandate_id"] is None]
    assert len(platform) == 1
    assert platform[0]["suggested_action"] == "check_control_plane"
    # The message must reassure rather than alarm: enforcement continues locally.
    assert "last signed policy" in platform[0]["detail"]


def test_attention_reports_stale_policy_delivery():
    stale = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    result = build_attention(
        [{"id": "a", "budget_usd": 100.0, "spent_usd": 1.0, "status": "active"}],
        policy_sync={"last_sync_error": None, "last_synced_at": stale},
    )
    assert any("minutes ago" in i["headline"] for i in result["items"])


def test_attention_handles_an_empty_ledger():
    result = build_attention([])
    assert result["status"] == "ok"
    assert result["headline"] == "No agents reporting yet"
    assert "mintry.init()" in result["subhead"]
