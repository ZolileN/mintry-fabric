"""Small example test showing how to spend an allocated budget.

This file can also be run as a script to write spend into a dashboard-backed DB:

    PYTHONPATH=src python3 tests/test_allocated_budget_usage.py --db test_data/local.db
"""

import argparse
import httpx
import mintry
import pytest
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict, cast

from mintry.core.dashboard import DashboardHandler
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet
from mintry.interceptors.global_http import GlobalHTTPInterceptor


class MeteredAllocatedBudgetDemoResult(TypedDict):
    db_path: str
    mandate_id: str
    spent_before: float
    spent_after: float
    dashboard_spent: float
    dashboard_remaining: float
    dashboard_total_remaining: float


class DashboardStats(TypedDict):
    total_mandates: int
    total_budget: float
    total_spent: float
    remaining_headroom: float


class DashboardMandateRow(TypedDict):
    id: str
    budget_usd: float
    spent_usd: float
    remaining_headroom: float
    status: str
    expires_at: str


class DashboardTopMandate(TypedDict):
    id: str
    spent_usd: float


class DashboardSummary(TypedDict):
    stats: DashboardStats
    top_mandates: list[DashboardTopMandate]
    mandates: list[DashboardMandateRow]
    history: list[dict[str, Any]]


@pytest.fixture(autouse=True)
def isolate_fabric() -> Iterator[None]:
    """Reset the global interceptor so tests stay isolated."""
    GlobalHTTPInterceptor._reset()
    yield
    GlobalHTTPInterceptor._reset()


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    """Provide a clean SQLite database path for the example test."""
    return str(tmp_path / "allocated_budget_example.db")


def get_dashboard_summary(db_path: str) -> DashboardSummary:
    """Read dashboard summary data for a specific database."""
    DashboardHandler.db_path = db_path
    dashboard = cast(DashboardHandler, object.__new__(DashboardHandler))
    return cast(DashboardSummary, dashboard.get_stats_data())


def run_metered_allocated_budget_demo(
    db_path: str = "test_data/local.db",
) -> MeteredAllocatedBudgetDemoResult:
    """Run a metered allocated-budget flow against a real SQLite DB.

    If the dashboard is already running against the same DB path, it will
    auto-refresh and show the updated spend from this demo.
    """
    GlobalHTTPInterceptor._reset()
    fabric = mintry.init(api_key="test_key_2026", db_path=db_path)
    mandate_id = "metered_allocated_job"

    existing = fabric.wallet.get_mandate(mandate_id)
    if existing["status"] == "unknown":
        fabric.wallet.create_mandate(mandate_id, 1.00)

    before = fabric.wallet.get_mandate(mandate_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "chatcmpl-allocated-metered",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-5-preview",
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 1000,
                    "total_tokens": 2000,
                },
                "choices": [{"message": {"role": "assistant", "content": "Metered."}}],
            },
            request=request,
        )

    with fabric.shield(mandate_id) as mandate:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-5-preview",
                    "messages": [{"role": "user", "content": "Generate a metered response."}],
                },
                headers={"X-Mintry-Mandate": mandate.id},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Metered request failed with status {response.status_code}")

    after = fabric.wallet.get_mandate(mandate_id)
    summary = get_dashboard_summary(db_path)
    dashboard_row = next(
        mandate for mandate in summary["mandates"] if mandate["id"] == mandate_id
    )

    return {
        "db_path": db_path,
        "mandate_id": mandate_id,
        "spent_before": cast(float, before["spent_usd"]),
        "spent_after": cast(float, after["spent_usd"]),
        "dashboard_spent": cast(float, dashboard_row["spent_usd"]),
        "dashboard_remaining": cast(float, dashboard_row["remaining_headroom"]),
        "dashboard_total_remaining": cast(float, summary["stats"]["remaining_headroom"]),
    }


def test_allocated_budget_can_be_reused_and_spent(temp_db: str) -> None:
    """Pre-allocate a named mandate, reuse it with shield(), and record spend."""
    wallet = MintryWallet(db_path=temp_db)
    engine = PolicyEngine(wallet)

    # Step 1: Allocate a named budget up front.
    wallet.create_mandate("allocated_test_job", 2.00)

    # Step 2: Reuse that exact mandate by calling shield() with the same task name.
    with engine.shield("allocated_test_job") as mandate:
        assert mandate.id == "allocated_test_job"
        assert mandate.max_usd == 2.00

        # Step 3: Confirm the mandate can still spend.
        assert engine.authorize(mandate.id, None, deduct=False) is True

    # Step 4: Simulate spend in the same way post-flight metering would.
    wallet.record_usage(mandate.id, 0.25)
    wallet.record_usage(mandate.id, 0.15)

    # Shared mandates stay active after use.
    state = wallet.get_mandate("allocated_test_job")
    assert state["status"] == "active"
    assert state["budget_usd"] == pytest.approx(2.00)
    assert state["spent_usd"] == pytest.approx(0.40)

    # The audit log shows the initial allocation plus two spend events.
    logs = wallet.get_audit_log("allocated_test_job")
    assert [log["action"] for log in logs] == ["create", "spend", "spend"]


def test_allocated_budget_can_be_spent_via_metered_openai_request(temp_db: str) -> None:
    """Allocate a named mandate, reuse it, and spend budget through the interceptor."""
    result = run_metered_allocated_budget_demo(temp_db)

    assert result["spent_before"] == pytest.approx(0.0)
    assert result["spent_after"] == pytest.approx(0.02, rel=1e-5)
    assert result["dashboard_spent"] == pytest.approx(0.02, rel=1e-5)
    assert result["dashboard_remaining"] == pytest.approx(0.98, rel=1e-5)

    wallet = MintryWallet(db_path=temp_db)
    final_state = wallet.get_mandate(result["mandate_id"])
    assert final_state["status"] == "active"
    assert final_state["budget_usd"] == pytest.approx(1.00)
    assert final_state["spent_usd"] == pytest.approx(0.02, rel=1e-5)

    logs = wallet.get_audit_log(result["mandate_id"])
    assert [log["action"] for log in logs] == ["create", "spend"]
    summary = get_dashboard_summary(temp_db)
    assert summary["stats"]["total_spent"] >= 0.02
    assert any(item["id"] == result["mandate_id"] for item in summary["top_mandates"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the allocated-budget metering demo.")
    parser.add_argument(
        "--db",
        default="test_data/local.db",
        help="SQLite DB path. Use the same path as the dashboard to see spend update there.",
    )
    args = parser.parse_args()

    result = run_metered_allocated_budget_demo(args.db)
    delta = result["spent_after"] - result["spent_before"]

    print(f"DB Path:          {result['db_path']}")
    print(f"Mandate ID:       {result['mandate_id']}")
    print(f"Spent Before:     ${result['spent_before']:.4f}")
    print(f"Spent After:      ${result['spent_after']:.4f}")
    print(f"Metered Delta:    ${delta:.4f}")
    print(f"Dashboard Spend:  ${result['dashboard_spent']:.4f}")
    print(f"Remaining:        ${result['dashboard_remaining']:.4f}")
    print(f"Total Headroom:   ${result['dashboard_total_remaining']:.4f}")
    print()
    print("If the dashboard is open against this same DB, it will refresh every 3 seconds")
    print("and show the updated spend automatically.")


if __name__ == "__main__":
    main()
