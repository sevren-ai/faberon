"""Research plan: the typed rulebook a campaign is governed by."""

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    """Typed research plan accepted by the control plane."""

    goal: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    metric_command: str = Field(min_length=1)
    baseline: float
    budget_gpu_hours: float = Field(gt=0)
    max_concurrency: int = Field(default=1, ge=1)
    walltime: int = Field(gt=0)  # in  minutes
    stop_conditions: list[str] = Field(min_length=1)
