"""Integration tests against a real Slurm cluster.

Unlike test_slurm_executor.py, these submit real jobs via sbatch and poll
sacct/squeue. They are skipped by default to avoid accidental job
submission. Opt in with FABERON_SLURM_INTEGRATION=1, typically on the
login node:

    FABERON_SLURM_INTEGRATION=1 uv run pytest -m slurm

These verify the Slurm contract the unit tests cannot: that the flags we
pass to sbatch/squeue/sacct/scancel are accepted and that real Slurm output
is parsed correctly.
"""

import os
import time
import uuid

import pytest

from faberon.executor import JobState, SubmitRequest
from faberon.executor.slurm import SlurmExecutor

pytestmark = [
    pytest.mark.slurm,
    pytest.mark.skipif(
        not os.environ.get("FABERON_SLURM_INTEGRATION"),
        reason="set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests",
    ),
]

_POLL_DEADLINE_S = 120
_POLL_INTERVAL_S = 1.0


def _wait_for_terminal(executor: SlurmExecutor, job_id: str) -> JobState:
    """Poll until the job reaches a terminal state, or time out."""
    deadline = time.monotonic() + _POLL_DEADLINE_S
    while time.monotonic() < deadline:
        info = executor.status(job_id)
        if info.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            return info.state
        time.sleep(_POLL_INTERVAL_S)
    raise AssertionError(f"job {job_id} did not finish within {_POLL_DEADLINE_S}s")


def _request(command: list[str], key: str) -> SubmitRequest:
    return SubmitRequest.model_validate({"command": command, "submission_key": key})


def test_submit_success():
    executor = SlurmExecutor()
    key = f"test-true-{uuid.uuid4().hex[:8]}"
    job_id = executor.submit(_request(["true"], key))
    assert _wait_for_terminal(executor, job_id) == JobState.COMPLETED
    assert executor.status(job_id).exit_code == 0


def test_submit_failure():
    executor = SlurmExecutor()
    key = f"test-false-{uuid.uuid4().hex[:8]}"
    job_id = executor.submit(_request(["false"], key))
    assert _wait_for_terminal(executor, job_id) == JobState.FAILED
    assert executor.status(job_id).exit_code != 0


def test_cancell():
    executor = SlurmExecutor()
    key = f"test-sleep-{uuid.uuid4().hex[:8]}"
    job_id = executor.submit(_request(["sleep", "300"], key))
    executor.cancel(job_id)
    assert _wait_for_terminal(executor, job_id) == JobState.CANCELLED


def test_submit_same_key():
    executor = SlurmExecutor()
    key = f"test-idem-{uuid.uuid4().hex[:8]}"
    first = executor.submit(_request(["true"], key))
    second = executor.submit(_request(["true"], key))
    assert first == second
