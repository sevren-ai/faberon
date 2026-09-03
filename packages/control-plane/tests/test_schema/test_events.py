"""Tests for faberon.schema.events."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from faberon.schema import Actor, Event, EventType


def test_event_round_trip():
    event = Event(
        campaign_id=uuid4(),
        actor=Actor.HUMAN,
        type=EventType.CAMPAIGN_CREATED,
        justification="Accepted plan after intake.",
        payload={"plan": {"metric_name": "val_bpb"}},
    )
    restored = Event.model_validate_json(event.model_dump_json())
    assert restored == event
    assert restored.payload["plan"]["metric_name"] == "val_bpb"


def test_event_requires_justification():
    with pytest.raises(ValidationError):
        Event(
            campaign_id=uuid4(),
            actor=Actor.AGENT,
            type=EventType.EXPERIMENT_SUBMITTED,
            justification="",
        )
