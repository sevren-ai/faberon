"""Tests for the Pydantic AI experiment proposer."""

import time
import uuid

import pytest
from pydantic_ai import ToolReturnPart, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from faberon.schema import Actor, Event, EventType
from faberon.workflow import AgentProposer, Proposal
from faberon.workflow.proposer import _ProposerLoop, _run_with_timeout

from .._fakes import FakeEvents
from ..conftest import make_plan


def test_proposer():
    campaign_id = uuid.uuid4()
    other_campaign_id = uuid.uuid4()
    judged = [
        Event(
            campaign_id=campaign_id,
            actor=Actor.AGENT,
            type=EventType.EXPERIMENT_JUDGED,
            reason=f"result number {index}",
            payload={"judgment": "keep", "metric_value": index / 10},
        )
        for index in range(12)
    ]
    proposed = Event(
        campaign_id=campaign_id,
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_PROPOSED,
        reason="earlier proposal",
        payload={},
    )
    other_campaign = Event(
        campaign_id=other_campaign_id,
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_JUDGED,
        reason="another campaign",
        payload={"judgment": "keep", "metric_value": 0.5},
    )
    events = FakeEvents([proposed, *judged, other_campaign])
    # dummy model
    dummy_output = "print('new experiment')\n"
    dummy_title = "Lower learning rate"
    dummy_rationale = "Try a smaller learning rate."
    model = TestModel(
        custom_output_args={
            "content": dummy_output,
            "title": dummy_title,
            "rationale": dummy_rationale,
        }
    )

    proposer = AgentProposer(events, model)
    try:
        with capture_run_messages() as messages:
            proposal = proposer.propose(
                campaign_id,
                make_plan(),
                "print('baseline')\n",
            )
    finally:
        proposer.close()
    # Ensure we're getting a correctly typed output object back
    assert proposal == Proposal(
        content=dummy_output,
        title=dummy_title,
        rationale=dummy_rationale,
    )
    # Ensure that the model used the correct tools
    assert model.last_model_request_parameters is not None
    tool_names = {
        tool.name for tool in model.last_model_request_parameters.function_tools
    }
    assert tool_names == {"read_target_file", "read_experiment_history"}
    # Ensure that no events from the other campaign were included
    history = next(
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name == "read_experiment_history"
    )
    assert history.content == [proposed, *judged]


def test_proposer_rejects_unchanged():
    content = "print('baseline')\n"
    model = TestModel(
        custom_output_args={
            "content": content,
            "title": "No change",
            "rationale": "No change.",
        }
    )

    proposer = AgentProposer(FakeEvents(), model)
    try:
        with pytest.raises(UnexpectedModelBehavior, match="maximum output retries"):
            proposer.propose(
                uuid.uuid4(),
                make_plan(),
                content,
            )
    finally:
        proposer.close()


def test_proposer_rejects_unparseable():
    # A model that emits broken Python (e.g. newlines collapsed by the
    # structured-output path) gets a retry instead of corrupting train.py.
    model = TestModel(
        custom_output_args={
            "content": "def train( nope\n",
            "title": "Broken Python",
            "rationale": "Broken Python.",
        }
    )

    proposer = AgentProposer(FakeEvents(), model)
    try:
        with pytest.raises(UnexpectedModelBehavior, match="maximum output retries"):
            proposer.propose(
                uuid.uuid4(),
                make_plan(),
                "print('baseline')\n",
            )
    finally:
        proposer.close()


def test_proposer_requires_model(monkeypatch):
    monkeypatch.delenv("FABERON_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="FABERON_MODEL is not set"):
        AgentProposer.from_env(FakeEvents())


async def _value(proposal: Proposal) -> Proposal:
    return proposal


def test_run_with_timeout_returns():
    loop = _ProposerLoop()
    try:
        proposal = Proposal(
            content="print('x')\n", title="a title", rationale="a rationale"
        )
        assert _run_with_timeout(loop, 5.0, lambda: _value(proposal)) == proposal
    finally:
        loop.close()


def test_run_with_timeout_raises():
    async def hang() -> Proposal:
        time.sleep(60)
        raise AssertionError("a timed-out call must not return")

    loop = _ProposerLoop()
    try:
        with pytest.raises(TimeoutError, match="exceeded"):
            _run_with_timeout(loop, 0.1, hang)
    finally:
        loop.close()


def test_run_with_timeout_reraises():
    async def boom() -> Proposal:
        raise ValueError("model broke")

    loop = _ProposerLoop()
    try:
        with pytest.raises(ValueError, match="model broke"):
            _run_with_timeout(loop, 5.0, boom)
    finally:
        loop.close()
