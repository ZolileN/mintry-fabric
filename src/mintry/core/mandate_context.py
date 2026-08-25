"""ContextVar-based mandate attribution for transparent LLM spend routing."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_active_mandate_id: ContextVar[Optional[str]] = ContextVar("mintry_active_mandate_id", default=None)


def get_active_mandate_id() -> Optional[str]:
    """Return the mandate ID bound to the current execution context, if any."""
    return _active_mandate_id.get()


def set_active_mandate_id(mandate_id: str) -> None:
    """Bind spend attribution for nested LLM calls until cleared."""
    _active_mandate_id.set(mandate_id)


def clear_active_mandate_id() -> None:
    """Remove context attribution (restores default / header routing)."""
    _active_mandate_id.set(None)


def resolve_default_mandate_id() -> str:
    """Sane default mandate — agent id or explicit override, never a $0.01 trap."""
    import os

    explicit = os.environ.get("MINTRY_DEFAULT_MANDATE", "").strip()
    if explicit:
        return explicit
    return os.environ.get("MINTRY_AGENT_ID", "default_agent").strip() or "default_agent"


def resolve_default_budget_usd() -> float:
    """Default ledger budget for the seeded default mandate."""
    import os

    raw = os.environ.get("MINTRY_DEFAULT_BUDGET_USD", "50.0").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 50.0
    return max(value, 0.01)


def resolve_mandate_id_from_request(request) -> str:
    """Header override → context mandate → sane default."""
    header = request.headers.get("x-mintry-mandate")
    if header:
        return header
    ctx = get_active_mandate_id()
    if ctx:
        return ctx
    return resolve_default_mandate_id()
