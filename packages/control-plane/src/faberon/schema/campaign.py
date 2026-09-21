"""The campaign record: one row per research campaign."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from .plan import ResearchPlan


class Campaign(BaseModel):
    """A campaign row: the anchor record for one research loop."""

    campaign_id: UUID
    workflow_id: str
    plan: ResearchPlan
    created_at: datetime
