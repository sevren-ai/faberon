"""Internal models used for durable workflow runs."""

from uuid import UUID

from pydantic import BaseModel, Field

from ..schema.plan import ResearchPlan


class ExperimentSetup(BaseModel):
    """Everything ``run_experiment`` needs for one job."""

    campaign_id: UUID
    command: list[str] = Field(min_length=1)
    submission_key: str = Field(min_length=1)
    metric_command: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    baseline: float
    poll_interval_seconds: float = Field(gt=0)
    walltime: int = Field(gt=0)  # in minutes


class CampaignSetup(BaseModel):
    """Everything ``run_campaign`` needs. Wraps the accepted plan."""

    campaign_id: UUID
    plan: ResearchPlan
    command: list[str] = Field(min_length=1)
    poll_interval_seconds: float = Field(default=30.0, gt=0)
    repo_path: str = Field(min_length=1, default=".")
    target_file: str = Field(min_length=1, default="train.py")
