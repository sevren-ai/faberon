"""Tests for the Pydantic AI experiment proposer."""

import time
import uuid

import pytest
from pydantic_ai import ToolReturnPart, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from faberon.schema.events import Actor, Event, EventType
from faberon.workflow import AgentProposer, Proposal
from faberon.workflow.proposer import _run_with_timeout

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
            justification=f"result {index}",
            payload={"judgment": "keep", "metric_value": index / 10},
        )
        for index in range(12)
    ]
    proposed = Event(
        campaign_id=campaign_id,
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_PROPOSED,
        justification="earlier proposal",
        payload={},
    )
    other_campaign = Event(
        campaign_id=other_campaign_id,
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_JUDGED,
        justification="another campaign",
        payload={"judgment": "keep", "metric_value": 0.5},
    )
    events = FakeEvents([proposed, *judged, other_campaign])
    # dummy model
    dummy_output = "print('new experiment')\n"
    dummy_rationale = "Try a smaller learning rate."
    model = TestModel(
        custom_output_args={
            "content": dummy_output,
            "rationale": dummy_rationale,
        }
    )

    with capture_run_messages() as messages:
        proposal = AgentProposer(events, model).propose(
            campaign_id,
            make_plan(),
            "print('baseline')\n",
        )
    # Ensure we're getting a correctly typed output object back
    assert proposal == Proposal(
        content=dummy_output,
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
            "rationale": "No change.",
        }
    )

    with pytest.raises(UnexpectedModelBehavior, match="maximum output retries"):
        AgentProposer(FakeEvents(), model).propose(
            uuid.uuid4(),
            make_plan(),
            content,
        )


def test_proposer_rejects_unparseable():
    # A model that emits broken Python (e.g. newlines collapsed by the
    # structured-output path) gets a retry instead of corrupting train.py.
    model = TestModel(
        custom_output_args={
            "content": "def train( nope\n",
            "rationale": "Broken Python.",
        }
    )

    with pytest.raises(UnexpectedModelBehavior, match="maximum output retries"):
        AgentProposer(FakeEvents(), model).propose(
            uuid.uuid4(),
            make_plan(),
            "print('baseline')\n",
        )


def test_proposer_requires_model(monkeypatch):
    monkeypatch.delenv("FABERON_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="FABERON_MODEL is not set"):
        AgentProposer.from_env(FakeEvents())


def test_run_with_timeout_returns():
    proposal = Proposal(content="print('x')\n", rationale="r")
    assert _run_with_timeout(5.0, lambda: proposal) == proposal


def test_run_with_timeout_raises():
    def hang() -> Proposal:
        time.sleep(60)
        raise AssertionError("a timed-out call must not return")

    with pytest.raises(TimeoutError, match="exceeded"):
        _run_with_timeout(0.1, hang)


def test_run_with_timeout_reraises():
    def boom() -> Proposal:
        raise ValueError("model broke")

    with pytest.raises(ValueError, match="model broke"):
        _run_with_timeout(5.0, boom)
