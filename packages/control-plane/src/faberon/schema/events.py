"""Ledger event record and event type vocabulary."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Actor(StrEnum):
    AGENT = "agent"
    HUMAN = "human"


class EventType(StrEnum):
    """Ledger event types."""

    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_ENDED = "campaign.ended"
    EXPERIMENT_PROPOSED = "experiment.proposed"
    EXPERIMENT_SUBMITTED = "experiment.submitted"
    EXPERIMENT_COMPLETED = "experiment.completed"
    EXPERIMENT_JUDGED = "experiment.judged"


class StopReason(StrEnum):
    """Why a campaign stopped."""

    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MAX_EXPERIMENTS = "max_experiments"


class Event(BaseModel):
    """Append-only ledger record."""

    seq: int | None = None  # position in the append-only log
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    campaign_id: UUID
    actor: Actor
    type: EventType
    justification: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
