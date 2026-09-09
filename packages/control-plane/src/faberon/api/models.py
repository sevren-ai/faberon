"""Request and response models for the HTTP API."""

from uuid import UUID

from pydantic import BaseModel, Field

from ..schema.events import Event
from ..schema.plan import ResearchPlan


class CampaignCreate(BaseModel):
    """POST /v0/campaigns body."""

    plan: ResearchPlan
    command: list[str] = Field(min_length=1)
    poll_interval_seconds: float = Field(default=30.0, gt=0)


class CampaignCreated(BaseModel):
    """POST /v0/campaigns result: new campaign ID and DBOS workflow ID."""

    campaign_id: UUID
    workflow_id: str


class CampaignStatus(BaseModel):
    """Minimal campaign view: ID plus ledger events for that campaign."""

    campaign_id: UUID
    events: list[Event]
