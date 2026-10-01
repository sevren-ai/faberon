"""External request and response models for the HTTP API."""

from uuid import UUID

from pydantic import BaseModel, Field

from ..schema.constants import MIN_PROSE_LENGTH
from ..schema.plan import ResearchPlan


class CampaignCreate(BaseModel):
    """POST /v0/campaigns body."""

    campaign_id: UUID
    plan: ResearchPlan
    command: list[str] = Field(min_length=1)
    repo_path: str = Field(min_length=1)
    poll_interval_seconds: float = Field(default=30.0, gt=0)


class CancelCampaign(BaseModel):
    """POST /v0/campaigns/{id}/cancel body."""

    justification: str = Field(min_length=MIN_PROSE_LENGTH)


class InjectIdea(BaseModel):
    """POST /v0/campaigns/{id}/ideas body."""

    text: str = Field(min_length=1)
    justification: str = Field(min_length=MIN_PROSE_LENGTH)


class CampaignCreated(BaseModel):
    """POST /v0/campaigns result: new campaign ID and DBOS workflow ID."""

    campaign_id: UUID
    workflow_id: str
