"""Opt-in integration test: run the proposer against the configured model."""

import ast
import uuid

import pytest
from pydantic_ai import ToolReturnPart, capture_run_messages

from faberon.schema import Actor, Event, EventType
from faberon.workflow import AgentProposer, Proposal

from .._fakes import FakeEvents
from ..conftest import make_plan

pytestmark = pytest.mark.llm

# A production-shaped target file.
_BASELINE = '''\
"""Autoresearch pretraining script. Single-GPU, single-file."""

import math

LEARNING_RATE = 1e-3
WARMUP_STEPS = 100
TOTAL_STEPS = 5000
MIN_LR_FRACTION = 0.1


def lr_at(step):
    """Linear warmup, then cosine decay to MIN_LR_FRACTION * LEARNING_RATE."""
    if step < WARMUP_STEPS:
        return LEARNING_RATE * (step + 1) / WARMUP_STEPS
    progress = min(1.0, (step - WARMUP_STEPS) / max(1, TOTAL_STEPS - WARMUP_STEPS))
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return LEARNING_RATE * (MIN_LR_FRACTION + (1.0 - MIN_LR_FRACTION) * cosine)


def train():
    # Use lr_at(step) as the optimizer learning rate at each training step.
    ...
'''


def test_proposer_with_llm():
    campaign_id = uuid.uuid4()
    events = FakeEvents(
        [
            Event(
                campaign_id=campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_JUDGED,
                reason="baseline run",
                payload={"judgment": "keep", "metric_value": 1.23},
            ),
            Event(
                campaign_id=campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_JUDGED,
                reason="lower learning rate",
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
    assert "read_experiment_history" in tools_used
