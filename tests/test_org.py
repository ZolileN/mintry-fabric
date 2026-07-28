"""Tests for org hierarchy → flat agent caps compilation."""

from __future__ import annotations

from mintry.core.fleet import FleetPartitionError, FleetPartitionPlan
from mintry.core.org import (
    OrgCompileError,
    OrgNode,
    compile_org_to_agent_caps,
    compile_org_to_fleet_plan,
    org_node_from_dict,
)


def test_compile_simple_company_to_agents():
    root = OrgNode(
        id="acme",
        kind="company",
        budget_usd=1000.0,
        children=(
            OrgNode(
                id="eng",
                kind="department",
                budget_usd=600.0,
                children=(
                    OrgNode(
                        id="chatbot",
                        kind="project",
                        children=(
                            OrgNode(id="agent_a", kind="agent", budget_usd=400.0),
                            OrgNode(id="agent_b", kind="agent"),  # gets remainder 200
                        ),
                    ),
                ),
            ),
            OrgNode(
                id="sales",
                kind="department",
                budget_usd=400.0,
                children=(OrgNode(id="agent_c", kind="agent"),),
            ),
        ),
    )
    caps = compile_org_to_agent_caps(root)
    assert isinstance(caps, dict)
    assert caps["agent_a"] == 400.0
    assert caps["agent_b"] == 200.0
    assert caps["agent_c"] == 400.0
    assert sum(caps.values()) == 1000.0


def test_child_exceeds_parent_rejected():
    root = {
        "id": "acme",
        "kind": "company",
        "budget_usd": 100.0,
        "children": [
            {
                "id": "eng",
                "kind": "department",
                "budget_usd": 200.0,
                "children": [{"id": "a1", "kind": "agent"}],
            }
        ],
    }
    err = compile_org_to_agent_caps(root)
    assert isinstance(err, OrgCompileError)


def test_compile_to_fleet_plan():
    root = {
        "id": "acme",
        "kind": "company",
        "budget_usd": 100.0,
        "children": [
            {
                "id": "eng",
                "kind": "department",
                "children": [
                    {"id": "alpha", "kind": "agent", "budget_usd": 40.0},
                    {"id": "beta", "kind": "agent", "budget_usd": 60.0},
                ],
            }
        ],
    }
    plan = compile_org_to_fleet_plan(root, fleet_id="acme-fleet")
    assert isinstance(plan, FleetPartitionPlan)
    assert plan.fleet_id == "acme-fleet"
    assert plan.partitions["alpha"] == 40.0
    assert plan.partitions["beta"] == 60.0


def test_org_node_from_dict_roundtrip():
    data = {
        "id": "acme",
        "kind": "company",
        "budget_usd": 50.0,
        "children": [{"id": "a1", "kind": "agent", "budget_usd": 50.0}],
    }
    node = org_node_from_dict(data)
    assert node.id == "acme"
    assert node.children[0].id == "a1"
