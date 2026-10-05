"""Tests for the local executor against real subprocesses.

These spawn real, short-lived processes (``sleep``, ``true``, ``false``) and
exercise submission, status, walltime enforcement, cancel, idempotency, and
restart reconciliation. They run anywhere and stay fast: walltime and the
cross-restart wait are simulated with sub-second deadlines rather than real
minute-scale sleeps.
"""

import json
import time
import uuid

import pytest

from faberon.executor import JobState, SubmitRequest
from faberon.executor.local import LocalExecutor

_POLL_DEADLINE_S = 10
_POLL_INTERVAL_S = 0.05


@pytest.fixture
def executor(tmp_path) -> LocalExecutor:
    return LocalExecutor(tmp_path / "state")


def _make_executor(state_dir, **kwargs) -> LocalExecutor:
    return LocalExecutor(state_dir, **kwargs)


def _request(command: str, key: str, *, walltime: int = 5) -> SubmitRequest:
    return SubmitRequest(
        command=command,
        submission_key=key,
        walltime=walltime,
        output_path=f"/tmp/faberon-test-{key}.out",
    )


def _key() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def _wait_terminal(executor: LocalExecutor, job_id: str):
    deadline = time.monotonic() + _POLL_DEADLINE_S
    while time.monotonic() < deadline:
        info = executor.status(job_id)
        if info.state.is_terminal:
            return info
        time.sleep(_POLL_INTERVAL_S)
    raise AssertionError(f"job {job_id} did not finish within {_POLL_DEADLINE_S}s")


def test_success(executor: LocalExecutor):
    job_id = executor.submit(_request("true", _key()))
    info = _wait_terminal(executor, job_id)
    assert info.state == JobState.COMPLETED
    assert info.exit_code == 0


def test_failure(executor: LocalExecutor):
    job_id = executor.submit(_request("false", _key()))
    info = _wait_terminal(executor, job_id)
    assert info.state == JobState.FAILED
    assert info.exit_code != 0


def test_nonzero_exit(executor: LocalExecutor):
    job_id = executor.submit(_request("sh -c 'exit 3'", _key()))
    info = _wait_terminal(executor, job_id)
    assert info.state == JobState.FAILED
    assert info.exit_code == 3


def test_terminal_reports_elapsed(executor: LocalExecutor):
    job_id = executor.submit(_request("sleep 0.2", _key()))
    info = _wait_terminal(executor, job_id)
    assert info.elapsed_seconds is not None
    assert info.elapsed_seconds >= 0.2


def test_output_file(executor: LocalExecutor, tmp_path):
    """The job's stdout/stderr log lands at the request's output_path."""
    key = _key()
    out = tmp_path / "repo" / ".faberon" / f"{key}.out"
    request = SubmitRequest(
        command="echo val_bpb: 1.10",
        submission_key=key,
        walltime=5,
        output_path=str(out),
    )
    job_id = executor.submit(request)
    assert job_id == key
    _wait_terminal(executor, job_id)
    assert "val_bpb: 1.10" in out.read_text()


def test_cancel(executor: LocalExecutor):
    job_id = executor.submit(_request("sleep 30", _key()))
    executor.cancel(job_id)
    info = executor.status(job_id)
    assert info.state == JobState.CANCELLED
    assert info.elapsed_seconds is not None


def test_walltime_enforcement(executor: LocalExecutor, tmp_path):
    """A job past its deadline is killed and reported FAILED."""
    key = _key()
    job_id = executor.submit(_request("sleep 30", key))
    # Simulate a nearly-expired deadline so the test does not sleep for minutes.
    record_path = tmp_path / "state" / f"{job_id}.json"
    record = json.loads(record_path.read_text())
    record["deadline"] = time.monotonic() + 0.1
    record_path.write_text(json.dumps(record))
    time.sleep(0.15)
    info = executor.status(job_id)
    assert info.state == JobState.FAILED
    assert info.exit_code is not None and info.exit_code != 0


def test_same_key_returns_same_id(executor: LocalExecutor):
    key = _key()
    first = executor.submit(_request("sleep 0.2", key))
    second = executor.submit(_request("echo other", key))
    assert first == second
    # The duplicate submit did not start a second process: only one runs.
    info = _wait_terminal(executor, first)
    assert info.state == JobState.COMPLETED


def test_idempotency_survives_restart(executor: LocalExecutor, tmp_path):
    """A new executor on the same state dir dedupes an in-flight submission."""
    key = _key()
    job_id = executor.submit(_request("sleep 0.3", key))
    restarted = _make_executor(tmp_path / "state")
    assert restarted.submit(_request("sleep 0.3", key)) == job_id
    executor.cancel(job_id)


def test_status_unknown_job(executor: LocalExecutor):
    with pytest.raises(KeyError):
        executor.status("no-such-job")


def test_restart_recovers_running_job(tmp_path):
    """A job started before a restart is still tracked and reapable after."""
    state_dir = tmp_path / "state"
    first = _make_executor(state_dir)
    job_id = first.submit(_request("sleep 0.3", _key()))

    # Simulate a control-plane restart: a fresh executor on the same dir.
    restarted = _make_executor(state_dir)
    assert restarted.status(job_id).state == JobState.RUNNING
    info = _wait_terminal(restarted, job_id)
    assert info.state == JobState.COMPLETED


def test_restart_recovers_finished_job(tmp_path):
    state_dir = tmp_path / "state"
    first = _make_executor(state_dir)
    job_id = first.submit(_request("true", _key()))
    _wait_terminal(first, job_id)

    restarted = _make_executor(state_dir)
    info = restarted.status(job_id)
    assert info.state == JobState.COMPLETED
    assert info.exit_code == 0


@pytest.mark.parametrize(
    "walltime,max_walltime,expected",
    [
        (120, None, 120),  # no cap set: request passes through
        (60, 240, 60),  # under the cap: unchanged
        (240, 120, 120),  # over the cap: clamped
        (120, 120, 120),  # exactly at the cap: unchanged
    ],
)
def test_effective_walltime(walltime, max_walltime, expected, tmp_path):
    executor = _make_executor(tmp_path / "state", max_walltime=max_walltime)
    request = _request("true", _key(), walltime=walltime)
    assert executor._effective_walltime(request) == expected
