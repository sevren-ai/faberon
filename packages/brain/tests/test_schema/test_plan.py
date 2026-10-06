"""Tests for faberon.schema.plan."""

import pytest
from pydantic import ValidationError

from faberon.schema import MIN_PROSE_LENGTH, ResearchPlan, resolve_target_in_repo


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


def test_plan_target_file_must_be_python():
    """The proposer's output is parsed as Python, so non-.py targets are rejected."""
    with pytest.raises(ValidationError):
        _minimal_plan(target_file="train.sh")
    plan = _minimal_plan(target_file="src/train.py")
    assert plan.target_file == "src/train.py"


def test_resolve_target_in_repo_accepts_nested(tmp_path):
    """A relative path that stays inside the repo resolves under it."""
    resolved = resolve_target_in_repo(str(tmp_path), "src/train.py")
    assert resolved == (tmp_path / "src/train.py").resolve()


def test_resolve_target_in_repo_rejects_absolute(tmp_path):
    with pytest.raises(ValueError, match="relative path"):
        resolve_target_in_repo(str(tmp_path), "/etc/passwd")


def test_resolve_target_in_repo_rejects_traversal(tmp_path):
    """``..`` that escapes the repo root is rejected."""
    with pytest.raises(ValueError, match="inside the repo"):
        resolve_target_in_repo(str(tmp_path), "../outside.py")


def test_resolve_target_in_repo_allows_inner_dotdot(tmp_path):
    """``..`` that stays inside the repo is fine."""
    resolved = resolve_target_in_repo(str(tmp_path), "sub/../train.py")
    assert resolved == (tmp_path / "train.py").resolve()
