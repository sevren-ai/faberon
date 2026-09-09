"""Inputs for a single durable experiment run."""

from uuid import UUID

from pydantic import BaseModel, Field


class ExperimentSetup(BaseModel):
    """Everything ``run_experiment`` needs for one job."""

    campaign_id: UUID
    command: list[str] = Field(min_length=1)
    submission_key: str = Field(min_length=1)
    metric_command: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    baseline: float
    poll_interval_seconds: float = Field(gt=0)
