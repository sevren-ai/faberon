"""Research plan: the typed rulebook a campaign is governed by (external model)"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .constants import MIN_PROSE_LENGTH


class ResearchPlan(BaseModel):
    """Typed research plan accepted by the Faberon brain."""

    goal: str = Field(min_length=MIN_PROSE_LENGTH)
    command: str = Field(min_length=1)
    target_file: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    baseline: float
    budget_gpu_hours: float = Field(gt=0)
    max_experiments: int = Field(ge=1)
    max_concurrency: int = Field(default=1, ge=1)
    walltime: int = Field(gt=0)  # in minutes
    stop_conditions: list[str] = Field(min_length=1)

    @field_validator("target_file")
    @classmethod
    def _target_is_python(cls, value: str) -> str:
        """The proposer's output is parsed as Python, so the target must be one."""
        if not value.lower().endswith(".py"):
            raise ValueError("target_file must be a Python file (.py)")
        return value


def resolve_target_in_repo(repo_path: str, target_file: str) -> Path:
    """Resolve the target file inside the repo, rejecting escape.

    The target must be a relative path whose resolved location stays under
    the resolved repo root. Rejects absolute paths and ``..`` traversal.
    """
    target = Path(target_file)
    if target.is_absolute():
        raise ValueError("target_file must be a relative path")
    repo = Path(repo_path).resolve()
    resolved = (repo / target).resolve()
    if not resolved.is_relative_to(repo):
        raise ValueError("target_file must stay inside the repo")
    return resolved
