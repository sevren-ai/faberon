"""Tests for faberon.executor."""

import pytest

from typing import assert_type

from faberon.executor import JobState, SubmitRequest, Executor

from mock_up import InMemoryExecutor

# Verify InMemoryExecutor satisfies the Executor protocol at import time.
assert_type(InMemoryExecutor(), Executor)


def _request(**overrides) -> SubmitRequest:
    data = {
        "command": ["echo", "hello"],
        "submission_key": "exp-1",
    }
    data.update(overrides)
    return SubmitRequest.model_validate(data)


def test_submit_status_complete():
    executor = InMemoryExecutor()
    job_id = executor.submit(_request())
    assert executor.status(job_id).state == JobState.RUNNING

    executor.complete(job_id, exit_code=0)
    done = executor.status(job_id)
    assert done.state == JobState.COMPLETED
    assert done.exit_code == 0


def test_submit_is_idempotent_on_submission_key():
    executor = InMemoryExecutor()
    first = executor.submit(_request(submission_key="same"))
    second = executor.submit(_request(submission_key="same", command=["echo", "other"]))
    assert first == second
    assert executor.status(first).state == JobState.RUNNING


def test_cancel_running_job():
    executor = InMemoryExecutor()
    job_id = executor.submit(_request())
    executor.cancel(job_id)
    assert executor.status(job_id).state == JobState.CANCELLED


def test_status_unknown_job_raises():
    executor = InMemoryExecutor()
    with pytest.raises(KeyError):
        executor.status("missing")
