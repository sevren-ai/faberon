"""The campaign record: one row per research campaign."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from .plan import ResearchPlan


class CampaignStatus(StrEnum):
    """Whether a campaign is running, finished, or died without an end event."""

    ACTIVE = "active"
    ENDED = "ended"
    DIED = "died"


class Campaign(BaseModel):
    """A campaign row: the anchor record for one research loop."""

    campaign_id: UUID
    workflow_id: str
    plan: ResearchPlan
    repo_path: str
    created_at: datetime


class CampaignInfo(BaseModel):
    """A campaign plus its live status: the API's view of one campaign."""

    campaign: Campaign
    status: CampaignStatus
    stop_reason: str | None = None
