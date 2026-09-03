"""Ledger event record and event type vocabulary."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Actor(StrEnum):
    AGENT = "agent"
    HUMAN = "human"


class EventType(StrEnum):
    """Ledger event types."""

    CAMPAIGN_CREATED = "campaign.created"
    EXPERIMENT_SUBMITTED = "experiment.submitted"
    EXPERIMENT_COMPLETED = "experiment.completed"
    EXPERIMENT_JUDGED = "experiment.judged"


class Event(BaseModel):
    """Append-only ledger record."""

    id: UUID = Field(default_factory=uuid4)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    campaign_id: UUID
    actor: Actor
    type: EventType
    justification: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
