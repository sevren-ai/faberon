"""Tests for faberon.schema.events."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from faberon.schema import (
    Actor,
    Event,
    EventType,
    StopReason,
)


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


def test_event_ended_stop_reason():
    # Raises if stop reason not present
    with pytest.raises(ValidationError):
        Event(
            campaign_id=uuid4(),
            actor=Actor.AGENT,
            type=EventType.CAMPAIGN_ENDED,
            justification="Reached max_experiments.",
        )
    # Raises if stop reason is not a valid enum value
    with pytest.raises(ValidationError):
        Event(
            campaign_id=uuid4(),
            actor=Actor.AGENT,
            type=EventType.CAMPAIGN_ENDED,
            justification="Reached max_experiments.",
            payload={"stop_reason": "not_a_stop_reason"},
        )

    # A JSON document with plain string values is accepted
    raw = {
        "campaign_id": "00000000-0000-4444-0000-000000000001",
        "actor": Actor.AGENT.value,
        "type": EventType.CAMPAIGN_ENDED.value,
        "justification": "Budget exhausted.",
        "payload": {"stop_reason": StopReason.BUDGET_EXHAUSTED.value},
    }
    event = Event.model_validate_json(json.dumps(raw))
    assert event.payload["stop_reason"] == StopReason.BUDGET_EXHAUSTED


def test_event_requires_justification():
    with pytest.raises(ValidationError):
        Event(
            campaign_id=uuid4(),
            actor=Actor.AGENT,
            type=EventType.EXPERIMENT_SUBMITTED,
            justification="",
        )


def test_event_justification_accepts_short_text():
    """An operational justification need only be non-empty."""
    event = Event(
        campaign_id=uuid4(),
        actor=Actor.HUMAN,
        type=EventType.CANCEL_REQUESTED,
        justification="no",
    )
    assert event.justification == "no"


def test_format_event():
    """Terse rendering is one line; verbose appends the payload."""
    event = Event(
        campaign_id=uuid4(),
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_JUDGED,
        justification="metric improved",
        payload={"judgment": "keep", "metric_value": 1.1},
    )
    terse = event.format()
    assert "experiment.judged" in terse
    assert "metric improved" in terse
    assert "keep" not in terse
    assert "\n" not in terse

    verbose = event.format(verbose=True)
    assert '"judgment": "keep"' in verbose
