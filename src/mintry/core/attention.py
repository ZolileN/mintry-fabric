"""Turns ledger state into the short list of things a human should look at.

The dashboard's job is to answer "is anything wrong?" — not to make a tenant
derive that from six KPI tiles. This module does that derivation once, server
side, so every client (web UI, CLI, digest email) gives the same answer.

This is the analytics layer described by Principle 6: it summarizes and ranks,
and is never consulted by the enforcement path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


# Utilization at which an agent moves from "watch" to "act".
CRITICAL_UTILIZATION = 0.95
WARNING_UTILIZATION = 0.80

# An agent holding this much unspent budget with no traffic is worth reclaiming.
IDLE_BUDGET_USD = 10.0

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _mandate_items(mandate: dict, now: datetime) -> list[dict]:
    """Every attention item raised by a single mandate."""
    mandate_id = mandate.get("id") or mandate.get("agent_id") or "unknown"
    budget = float(mandate.get("budget_usd") or 0.0)
    spent = float(mandate.get("spent_usd") or 0.0)
    status = (mandate.get("status") or "unknown").lower()
    remaining = budget - spent
    utilization = (spent / budget) if budget > 0 else 0.0
    items: list[dict] = []

    def item(severity: str, headline: str, detail: str, action: str) -> dict:
        return {
            "severity": severity,
            "mandate_id": mandate_id,
            "headline": headline,
            "detail": detail,
            "suggested_action": action,
            "utilization": round(utilization, 4),
            "budget_usd": round(budget, 4),
            "spent_usd": round(spent, 4),
            "remaining_usd": round(remaining, 4),
        }

    if status == "exhausted":
        items.append(item(
            "critical",
            f"{mandate_id} is out of budget and its requests are being blocked",
            f"Spent {_money(spent)} of {_money(budget)}.",
            "raise_budget",
        ))
    elif status == "expired":
        items.append(item(
            "critical",
            f"{mandate_id} has expired and its requests are being blocked",
            f"Spent {_money(spent)} of {_money(budget)} before expiry.",
            "extend_expiry",
        ))
    elif budget > 0 and utilization >= CRITICAL_UTILIZATION:
        items.append(item(
            "critical",
            f"{mandate_id} has {_money(remaining)} left and will start blocking soon",
            f"Used {utilization * 100:.0f}% of {_money(budget)}.",
            "raise_budget",
        ))
    elif budget > 0 and utilization >= WARNING_UTILIZATION:
        items.append(item(
            "warning",
            f"{mandate_id} has used {utilization * 100:.0f}% of its budget",
            f"{_money(remaining)} of {_money(budget)} left.",
            "raise_budget",
        ))

    expires_at = _parse_ts(mandate.get("expires_at"))
    if expires_at and status not in ("expired", "exhausted"):
        hours_left = (expires_at - now).total_seconds() / 3600.0
        if 0 < hours_left <= 24:
            items.append(item(
                "warning",
                f"{mandate_id} expires in {hours_left:.0f}h",
                f"After {expires_at.isoformat()} its requests are blocked.",
                "extend_expiry",
            ))

    if status == "active" and spent == 0.0 and budget >= IDLE_BUDGET_USD:
        items.append(item(
            "info",
            f"{mandate_id} is holding {_money(budget)} it has never spent",
            "No metered traffic against this budget yet.",
            "reclaim_budget",
        ))

    return items


def _sync_items(policy_sync: Optional[dict], now: datetime, max_stale_minutes: float) -> list[dict]:
    """Attention items about policy distribution rather than any one agent."""
    if not policy_sync:
        return []

    items: list[dict] = []
    last_error = policy_sync.get("last_sync_error")
    last_synced = _parse_ts(policy_sync.get("last_synced_at"))

    if last_error:
        items.append({
            "severity": "warning",
            "mandate_id": None,
            "headline": "New policy versions are not reaching your agents",
            "detail": (
                f"Last sync attempt failed: {last_error}. Agents keep enforcing the "
                "last signed policy, so nothing is running uncapped."
            ),
            "suggested_action": "check_control_plane",
        })
    elif last_synced is not None:
        stale_minutes = (now - last_synced).total_seconds() / 60.0
        if stale_minutes > max_stale_minutes:
            items.append({
                "severity": "warning",
                "mandate_id": None,
                "headline": f"Policy last reached your agents {stale_minutes:.0f} minutes ago",
                "detail": (
                    "Budget changes you make now may not take effect. Agents keep "
                    "enforcing the last signed policy."
                ),
                "suggested_action": "check_control_plane",
            })

    return items


def build_attention(
    mandates: list[dict],
    policy_sync: Optional[dict] = None,
    now: Optional[datetime] = None,
    max_stale_minutes: float = 10.0,
) -> dict:
    """Summarize what, if anything, needs a human.

    Returns a status (``ok`` / ``watch`` / ``action_required``), a plain-language
    headline, and the ranked items behind it.
    """
    now = now or datetime.now(timezone.utc)
    mandates = mandates or []

    items: list[dict] = []
    for mandate in mandates:
        items.extend(_mandate_items(mandate, now))
    items.extend(_sync_items(policy_sync, now, max_stale_minutes))

    items.sort(key=lambda i: (
        SEVERITY_ORDER.get(i.get("severity", "info"), 3),
        -float(i.get("utilization") or 0.0),
    ))

    critical = sum(1 for i in items if i["severity"] == "critical")
    warning = sum(1 for i in items if i["severity"] == "warning")

    if critical:
        status = "action_required"
    elif warning:
        status = "watch"
    else:
        status = "ok"

    total = len(mandates)
    agent_word = "agent" if total == 1 else "agents"

    if status == "action_required":
        subject = "agent needs" if critical == 1 else "agents need"
        headline = f"{critical} {subject} your attention"
        subhead = "Requests are being blocked or are about to be."
    elif status == "watch":
        subject = "agent is" if warning == 1 else "agents are"
        headline = f"{warning} {subject} approaching its budget"
        subhead = "Nothing is blocked. We will keep watching and alert you if that changes."
    else:
        headline = f"All {total} {agent_word} are within budget" if total else "No agents reporting yet"
        subhead = (
            "Nothing needs you right now — we alert you before a budget runs out."
            if total
            else "Call mintry.init() in an application to start seeing spend here."
        )

    return {
        "status": status,
        "headline": headline,
        "subhead": subhead,
        "critical_count": critical,
        "warning_count": warning,
        "items": items,
    }
