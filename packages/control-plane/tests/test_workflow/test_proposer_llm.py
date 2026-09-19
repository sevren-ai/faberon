"""Opt-in integration test: run the proposer against the configured model."""

import ast
import uuid

import pytest
from pydantic_ai import ToolReturnPart, capture_run_messages

from faberon.schema.events import Actor, Event, EventType
from faberon.workflow import AgentProposer, Proposal

from .._fakes import FakeEvents
from ..conftest import make_plan

pytestmark = pytest.mark.llm

_BASELINE = "LEARNING_RATE = 1e-3\n\n\ndef train():\n    ...\n"


def test_proposer_with_llm():
    campaign_id = uuid.uuid4()
    events = FakeEvents(
        [
            Event(
                campaign_id=campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_JUDGED,
                justification="baseline run",
                payload={"judgment": "keep", "metric_value": 1.23},
            ),
            Event(
                campaign_id=campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_JUDGED,
                justification="lower learning rate",
                payload={"judgment": "keep", "metric_value": 1.10},
            ),
        ]
    )
    proposer = AgentProposer.from_env(events)

    with capture_run_messages() as messages:
        proposal = proposer.propose(campaign_id, make_plan(), _BASELINE)
    assert isinstance(proposal, Proposal)

    # Ensure this is parseable Python
    ast.parse(proposal.content)

    # The model read the file and the history instead of proposing blind.
    tools_used = {
        part.tool_name
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    assert tools_used == {"read_target_file", "read_experiment_history"}
