"""Tests for Fleet Option A static partition validation."""

from __future__ import annotations

import pytest

from mintry.core.fleet import (
    FleetPartitionError,
    FleetPartitionPlan,
    mandate_rule_for_share,
    validate_partitions,
)


def test_valid_exact_partition():
    plan = validate_partitions(
        100.0,
        {"alpha": 40.0, "beta": 60.0},
        fleet_id="prod",
    )
    assert isinstance(plan, FleetPartitionPlan)
    assert plan.fleet_id == "prod"
    assert plan.allocated_usd == 100.0
    assert plan.unallocated_usd == 0.0
    assert plan.partitions == {"alpha": 40.0, "beta": 60.0}


def test_undersubscribe_keeps_unallocated_headroom():
    plan = validate_partitions(1000.0, {"a": 100.0, "b": 200.0}, fleet_id="fleet-1")
    assert isinstance(plan, FleetPartitionPlan)
    assert plan.allocated_usd == 300.0
    assert plan.unallocated_usd == 700.0


def test_oversubscribe_rejected():
    err = validate_partitions(100.0, {"a": 60.0, "b": 50.0})
    assert isinstance(err, FleetPartitionError)
    assert "oversubscribed" in str(err)


def test_empty_partitions_rejected():
    err = validate_partitions(100.0, {})
    assert isinstance(err, FleetPartitionError)


def test_share_below_minimum_rejected():
    err = validate_partitions(100.0, {"a": 0.001})
    assert isinstance(err, FleetPartitionError)
    assert "0.01" in str(err)


def test_blank_agent_id_rejected():
    err = validate_partitions(100.0, {"  ": 10.0})
    assert isinstance(err, FleetPartitionError)


def test_mandate_rule_embeds_fleet_metadata():
    rule = mandate_rule_for_share(25.0, fleet_id="prod", fleet_total_usd=100.0)
    assert rule == {
        "max_usd": 25.0,
        "allow": True,
        "fleet_id": "prod",
        "fleet_total_usd": 100.0,
    }


@pytest.mark.parametrize(
    "total,partitions",
    [
        (-1.0, {"a": 1.0}),
        (float("nan"), {"a": 1.0}),
        (100.0, {"a": float("inf")}),
    ],
)
def test_non_finite_rejected(total, partitions):
    err = validate_partitions(total, partitions)
    assert isinstance(err, FleetPartitionError)
