"""Fleet Option A — static sub-budget partitioning.

Authors split a fleet total into per-agent shares at the control plane.
Each agent then enforces only its local ``max_usd`` (Principle 3 + 6).
No shared counter and no network I/O on the authorize hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


MIN_SHARE_USD = 0.01
_EPSILON = 1e-9


@dataclass(frozen=True)
class FleetPartitionError:
    """Validation failure for a proposed fleet partition."""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class FleetPartitionPlan:
    """Validated static partition ready to author as per-agent policies."""

    fleet_id: str
    total_usd: float
    partitions: dict[str, float]
    allocated_usd: float
    unallocated_usd: float


def validate_partitions(
    total_usd: float,
    partitions: Mapping[str, float],
    *,
    fleet_id: str = "",
    min_share_usd: float = MIN_SHARE_USD,
) -> FleetPartitionPlan | FleetPartitionError:
    """Validate Option A static partitions.

    Accepted when:
    - ``total_usd`` is finite and >= ``min_share_usd``
    - ``partitions`` is a non-empty map of agent_id → share
    - every agent_id is a non-empty string
    - every share is finite and >= ``min_share_usd``
    - ``sum(shares) <= total_usd`` (undersubscribe keeps unallocated headroom)

    Rejected when the fleet is oversubscribed (``sum > total``).
    """
    if not isinstance(total_usd, (int, float)) or isinstance(total_usd, bool):
        return FleetPartitionError("total_usd must be a number")
    total = float(total_usd)
    if total != total or total in (float("inf"), float("-inf")):  # NaN / inf
        return FleetPartitionError("total_usd must be finite")
    if total < min_share_usd:
        return FleetPartitionError(
            f"total_usd must be >= {min_share_usd:.2f} (got {total})"
        )

    if not isinstance(partitions, Mapping) or isinstance(partitions, (str, bytes)):
        return FleetPartitionError("partitions must be an object map of agent_id → share_usd")
    if not partitions:
        return FleetPartitionError("partitions must include at least one agent")

    normalized: dict[str, float] = {}
    for raw_agent, raw_share in partitions.items():
        agent_id = str(raw_agent).strip() if raw_agent is not None else ""
        if not agent_id:
            return FleetPartitionError("every partition key must be a non-empty agent_id")
        if not isinstance(raw_share, (int, float)) or isinstance(raw_share, bool):
            return FleetPartitionError(f"share for agent {agent_id!r} must be a number")
        share = float(raw_share)
        if share != share or share in (float("inf"), float("-inf")):
            return FleetPartitionError(f"share for agent {agent_id!r} must be finite")
        if share < min_share_usd:
            return FleetPartitionError(
                f"share for agent {agent_id!r} must be >= {min_share_usd:.2f} (got {share})"
            )
        if agent_id in normalized:
            return FleetPartitionError(f"duplicate agent_id in partitions: {agent_id!r}")
        normalized[agent_id] = round(share, 6)

    allocated = round(sum(normalized.values()), 6)
    if allocated > total + _EPSILON:
        return FleetPartitionError(
            f"fleet oversubscribed: allocated ${allocated:.4f} exceeds total ${total:.4f}"
        )

    fid = (fleet_id or "").strip()
    return FleetPartitionPlan(
        fleet_id=fid,
        total_usd=round(total, 6),
        partitions=normalized,
        allocated_usd=allocated,
        unallocated_usd=round(max(total - allocated, 0.0), 6),
    )


def mandate_rule_for_share(
    share_usd: float,
    *,
    fleet_id: str = "",
    fleet_total_usd: float | None = None,
) -> dict:
    """Build the flat mandate rule embedded in a per-agent policy bundle.

    Extra fleet metadata is informational for audit/UI. The hot path only
    consumes ``max_usd`` / ``allow`` / ``expires_at``.
    """
    rule: dict = {"max_usd": float(share_usd), "allow": True}
    if fleet_id:
        rule["fleet_id"] = fleet_id
    if fleet_total_usd is not None:
        rule["fleet_total_usd"] = float(fleet_total_usd)
    return rule
