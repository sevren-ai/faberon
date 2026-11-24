"""Progress derivation: GPU-hours burned from ledger events."""

import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest

from faberon.schema.campaign import Campaign
from faberon.schema.events import Actor, Event, EventType
from faberon.workflow.status import _derive_progress

from ..conftest import make_plan


def _campaign() -> Campaign:
    return Campaign(
        campaign_id=uuid.uuid4(),
        workflow_id="wf-test",
        plan=make_plan(),
        repo_path="/repo",
        branch="main",
        start_sha="0" * 40,
        poll_interval_seconds=1.0,
        created_at=datetime.now(UTC),
    )


def _completed(campaign_id: UUID, elapsed_seconds: float, gpus: int) -> Event:
    payload = {
        "job_id": "j",
        "index": 1,
        "sha": "0" * 40,
        "command": "echo hello",
        "state": "completed",
        "exit_code": 0,
        "elapsed_seconds": elapsed_seconds,
        "gpus": gpus,
    }
    return Event(
        campaign_id=campaign_id,
        actor=Actor.AGENT,
        type=EventType.EXPERIMENT_COMPLETED,
        reason="job j completed exit=0",
        payload=payload,
    )


def test_progress_gpu_hours():
    # Each job's elapsed seconds are multiplied by its own GPU count, and
    # jobs that overlap in wall time still each burn their own GPU-hours.
    campaign = _campaign()
    events = [
        _completed(campaign.campaign_id, 3600.0, gpus=2),
        _completed(campaign.campaign_id, 1800.0, gpus=8),
    ]
    progress = _derive_progress(campaign, events)
    assert progress.gpu_hours_burned == pytest.approx(2.0 + 4.0)
