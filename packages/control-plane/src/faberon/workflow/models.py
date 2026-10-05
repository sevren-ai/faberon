"""Internal models used for durable workflow runs."""

from uuid import UUID

from pydantic import BaseModel, Field

from ..executor import JobInfo
from ..schema.constants import MIN_PROSE_LENGTH
from ..schema.plan import ResearchPlan


class Proposal(BaseModel):
    """Validated replacement content, its summary/title, and its research rationale."""

    content: str = Field(min_length=1)
    title: str = Field(min_length=3, max_length=55)
    rationale: str = Field(min_length=MIN_PROSE_LENGTH)


class ExperimentResult(BaseModel):
    """Outcome of one experiment: judgment, metric, and the final job info."""

    judgment: str
    metric_value: float | None
    job_info: JobInfo


class ExperimentSetup(BaseModel):
    """Everything ``run_experiment`` needs for one job."""

    campaign_id: UUID
    command: str = Field(min_length=1)
    submission_key: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    repo_path: str = Field(min_length=1)
    baseline: float
    poll_interval_seconds: float = Field(gt=0)
    walltime: int = Field(gt=0)  # in minutes
    index: int = Field(ge=1)
    sha: str = Field(min_length=1)


class CampaignSetup(BaseModel):
    """Everything ``run_campaign`` needs. Wraps the accepted plan."""

    campaign_id: UUID
    plan: ResearchPlan
    poll_interval_seconds: float = Field(default=30.0, gt=0)
    repo_path: str = Field(min_length=1, default=".")
    target_file: str = Field(min_length=1, default="train.py")
