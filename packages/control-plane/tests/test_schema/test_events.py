"""Tests for faberon.schema.events."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from faberon.schema import Actor, Event, EventType, StopReason


def test_event_round_trip():
    event = Event(
        campaign_id=uuid4(),
        actor=Actor.AGENT,
        type=EventType.CAMPAIGN_ENDED,
        justification="Reached max_experiments.",
        payload={"stop_reason": StopReason.MAX_EXPERIMENTS},
    )
    restored = Event.model_validate_json(event.model_dump_json())
    assert restored == event
    assert restored.payload["stop_reason"] == StopReason.MAX_EXPERIMENTS


def test_event_requires_justification():
    with pytest.raises(ValidationError):
        Event(
            campaign_id=uuid4(),
            actor=Actor.AGENT,
            type=EventType.EXPERIMENT_SUBMITTED,
            justification="",
        )
