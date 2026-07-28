"""Organization hierarchy → flat per-agent caps (Phase 2 E2).

Company → department → project → agent budget inheritance is compiled
at author/sync time into flat ``agent_id → max_usd`` numbers.
The enforcement hot path never walks the tree (Principle 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from mintry.core.fleet import (
    FleetPartitionError,
    FleetPartitionPlan,
    validate_partitions,
)


@dataclass(frozen=True)
class OrgNode:
    """A node in the org budget tree."""

    id: str
    kind: str  # company | department | project | agent
    budget_usd: Optional[float] = None  # explicit ceiling; None = inherit parent remainder share
    children: tuple["OrgNode", ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrgCompileError:
    message: str

    def __str__(self) -> str:
        return self.message


def _validate_node(node: OrgNode, *, path: str = "") -> Optional[OrgCompileError]:
    here = f"{path}/{node.id}" if path else node.id
    if not node.id or not str(node.id).strip():
        return OrgCompileError(f"org node at {here or '<root>'} missing id")
    if node.kind not in {"company", "department", "project", "agent"}:
        return OrgCompileError(f"org node {here!r} has invalid kind {node.kind!r}")
    if node.budget_usd is not None:
        if not isinstance(node.budget_usd, (int, float)) or isinstance(node.budget_usd, bool):
            return OrgCompileError(f"org node {here!r} budget_usd must be a number")
        if float(node.budget_usd) < 0:
            return OrgCompileError(f"org node {here!r} budget_usd must be >= 0")
    if node.kind == "agent" and node.children:
        return OrgCompileError(f"agent node {here!r} cannot have children")
    for child in node.children:
        err = _validate_node(child, path=here)
        if err:
            return err
    return None


def _collect_agent_caps(
    node: OrgNode,
    parent_budget: float,
    out: dict[str, float],
) -> Optional[OrgCompileError]:
    """Walk the tree; agent leaves get an explicit flat max_usd."""
    own = float(node.budget_usd) if node.budget_usd is not None else parent_budget
    if own > parent_budget + 1e-9 and node.budget_usd is not None:
        return OrgCompileError(
            f"node {node.id!r} budget ${own:.4f} exceeds parent budget ${parent_budget:.4f}"
        )

    if node.kind == "agent":
        if node.id in out:
            return OrgCompileError(f"duplicate agent id in org tree: {node.id!r}")
        out[node.id] = round(own, 6)
        return None

    if not node.children:
        return OrgCompileError(f"non-agent node {node.id!r} has no children")

    # Children with explicit budgets consume from own; remainder split equally
    # among children without explicit budgets.
    explicit = [c for c in node.children if c.budget_usd is not None]
    implicit = [c for c in node.children if c.budget_usd is None]
    explicit_sum = sum(float(c.budget_usd or 0.0) for c in explicit)
    if explicit_sum > own + 1e-9:
        return OrgCompileError(
            f"children of {node.id!r} explicit budgets ${explicit_sum:.4f} exceed node budget ${own:.4f}"
        )
    remainder = own - explicit_sum
    per_implicit = (remainder / len(implicit)) if implicit else 0.0

    for child in node.children:
        child_parent = float(child.budget_usd) if child.budget_usd is not None else per_implicit
        # Pass the child's allocated slice as its parent_budget for recursion.
        # If child has explicit budget, that is the ceiling; else equal share of remainder.
        err = _collect_agent_caps(child, child_parent if child.budget_usd is not None else per_implicit, out)
        if err:
            return err
    return None


def org_node_from_dict(data: Mapping[str, Any]) -> OrgNode:
    """Parse a nested org tree from a JSON-compatible dict."""
    children_raw = data.get("children") or []
    children = tuple(org_node_from_dict(c) for c in children_raw)
    return OrgNode(
        id=str(data.get("id", "")),
        kind=str(data.get("kind", "")),
        budget_usd=data.get("budget_usd"),
        children=children,
        metadata=data.get("metadata") or {},
    )


def compile_org_to_agent_caps(
    root: OrgNode | Mapping[str, Any],
) -> dict[str, float] | OrgCompileError:
    """Compile an org tree into flat ``agent_id → max_usd`` caps.

    The result is suitable for Fleet Option A / per-agent policy mandates.
    """
    node = root if isinstance(root, OrgNode) else org_node_from_dict(root)
    err = _validate_node(node)
    if err:
        return err
    if node.kind != "company":
        return OrgCompileError("org root must be kind='company'")
    if node.budget_usd is None:
        return OrgCompileError("company root must declare budget_usd")

    caps: dict[str, float] = {}
    err = _collect_agent_caps(node, float(node.budget_usd), caps)
    if err:
        return err
    if not caps:
        return OrgCompileError("org tree produced no agent caps")
    return caps


def compile_org_to_fleet_plan(
    root: OrgNode | Mapping[str, Any],
    *,
    fleet_id: str,
) -> FleetPartitionPlan | FleetPartitionError | OrgCompileError:
    """Compile org hierarchy into a validated FleetPartitionPlan."""
    caps = compile_org_to_agent_caps(root)
    if isinstance(caps, OrgCompileError):
        return caps
    node = root if isinstance(root, OrgNode) else org_node_from_dict(root)
    total = float(node.budget_usd or 0.0)
    return validate_partitions(total, caps, fleet_id=fleet_id)
