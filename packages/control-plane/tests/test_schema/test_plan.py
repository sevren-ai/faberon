"""Tests for faberon.schema.plan."""

import pytest
from pydantic import ValidationError

from faberon.schema import ResearchPlan


def _minimal_plan(**overrides) -> ResearchPlan:
    data = {
        "goal": "Beat the measured val_bpb baseline on autoresearch.",
        "metric_name": "val_bpb",
        "metric_command": "uv run train.py --eval-only",
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


def test_plan_rejects_non_positive_budget():
    with pytest.raises(ValidationError):
        _minimal_plan(budget_gpu_hours=0)


def test_plan_rejects_non_positive_max_experiments():
    with pytest.raises(ValidationError):
        _minimal_plan(max_experiments=0)
