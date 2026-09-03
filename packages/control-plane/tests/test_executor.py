"""Tests for faberon.executor."""

import pytest

from faberon.executor import Executor, JobState, SubmitRequest
from mock_up import InMemoryExecutor


def _request(**overrides) -> SubmitRequest:
    data = {
        "command": ["echo", "hello"],
        "submission_key": "exp-1",
    }
    data.update(overrides)
    return SubmitRequest.model_validate(data)


def test_inmemory_executor():
    executor = InMemoryExecutor()

    # Verify InMemoryExecutor satisfies the Executor protocol
    _check: Executor = executor

    # submit -> RUNNING
    job_id = executor.submit(_request(submission_key="my_bestest_job"))
    assert executor.status(job_id).state == JobState.RUNNING

    # complete -> COMPLETED
    executor.complete(job_id, exit_code=0)
    done = executor.status(job_id)
    assert done.state == JobState.COMPLETED
    assert done.exit_code == 0
    assert executor.status(job_id).state == JobState.COMPLETED

    # submit duplicate -> idempotent
    job_id_2 = executor.submit(_request(submission_key="my_bestest_job"))
    assert job_id == job_id_2
    assert executor.status(job_id_2).state == JobState.COMPLETED

    # submit new job -> different ID
    job_id_3 = executor.submit(_request(submission_key="some_awful_job"))
    assert job_id != job_id_3
    assert executor.status(job_id_3).state == JobState.RUNNING

    # cancel -> CANCELED
    executor.cancel(job_id_3)
    assert executor.status(job_id_3).state == JobState.CANCELLED

    # unknown ID -> raises
    with pytest.raises(KeyError):
        executor.status("weird_ID")
