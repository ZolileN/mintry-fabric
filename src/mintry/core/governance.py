"""Helpers for governance mode (central Sign & Push vs local ledger edits)."""

from __future__ import annotations

import os


def control_plane_configured() -> bool:
    return bool(os.environ.get("MINTRY_CONTROL_PLANE_URL", "").strip())


def local_governance_enabled() -> bool:
    """Whether in-place SQLite mandate upsert/revoke is allowed.

    When a control plane URL is configured, local mutations require explicit
    ``MINTRY_LOCAL_GOVERNANCE=1`` (or the legacy
    ``MINTRY_REQUIRE_LOCAL_GOVERNANCE_FLAG`` opt-out path is not needed —
    CP presence itself implies the gate).

    Local-only / air-gapped agents (no CP URL) keep local upsert for ops.
    """
    if os.environ.get("MINTRY_LOCAL_GOVERNANCE", "").lower() in ("1", "true", "yes"):
        return True
    # Explicit force-gate even without CP (stricter local demos)
    if os.environ.get("MINTRY_REQUIRE_LOCAL_GOVERNANCE_FLAG", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    # No control plane → local ledger is the only authoring surface
    if not control_plane_configured():
        return True
    # Control plane configured → central Sign & Push is source of truth
    return False


def local_governance_denied_message() -> str:
    return (
        "Local mandate mutations disabled while a control plane is configured. "
        "Author caps via Sign & Push (or Fleet/Org compile), "
        "or set MINTRY_LOCAL_GOVERNANCE=1 for local ledger edits."
    )
