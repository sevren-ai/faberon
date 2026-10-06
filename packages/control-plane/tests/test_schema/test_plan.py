"""Tests for faberon.schema.plan."""

import pytest
from pydantic import ValidationError

from faberon.schema import MIN_PROSE_LENGTH, ResearchPlan


def _minimal_plan(**overrides) -> ResearchPlan:
    data = {
        "goal": "Beat the measured val_bpb baseline on autoresearch.",
        "command": "uv run train.py",
        "target_file": "train.py",
        "metric": "val_bpb",
        "baseline": 1.23,
        "budget_gpu_hours": 10.0,
        "max_experiments": 6,
        "max_concurrency": 1,
        "walltime": 10,
        "stop_conditions": ["budget exhausted"],
    }
    data.update(overrides)
    return ResearchPlan.model_validate(data)


def test_plan_round_trip():
    plan = _minimal_plan()
    restored = ResearchPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan


def test_plan_rejects_blank_goal():
    with pytest.raises(ValidationError):
        _minimal_plan(goal="")


def test_plan_goal_min_length():
    """A goal below the prose floor is rejected; one at the floor passes."""
    with pytest.raises(ValidationError):
        _minimal_plan(goal="x" * (MIN_PROSE_LENGTH - 1))
    plan = _minimal_plan(goal="x" * MIN_PROSE_LENGTH)
    assert len(plan.goal) == MIN_PROSE_LENGTH


def test_plan_rejects_non_positive_budget():
    with pytest.raises(ValidationError):
        _minimal_plan(budget_gpu_hours=0)


def test_plan_rejects_non_positive_max_experiments():
    with pytest.raises(ValidationError):
        _minimal_plan(max_experiments=0)


def test_plan_requires_target_file():
    """The plan names the file the proposer edits; there is no hidden default."""
    data = _minimal_plan().model_dump(mode="json")
    del data["target_file"]
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(data)
    with pytest.raises(ValidationError):
        _minimal_plan(target_file="")
