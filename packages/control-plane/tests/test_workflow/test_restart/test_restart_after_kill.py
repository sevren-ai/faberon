"""Kill-mid-run restart test.

Starts the control plane in a subprocess, lets it submit a job and enter the
durable poll loop, kills the process, restarts a fresh process, and verifies
that the workflow restarts without resubmitting and judges/logs exactly once.

Requires a real Postgres (``FABERON_DATABASE_URL``) for the DBOS checkpoints
and the ledger.

This test uses a file-backed fake executor to stand in for the cluster, so it
verifies the control-plane-side durability (DBOS recovery + exactly-once
ledger) in CI.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from faberon.ledger import Ledger
from faberon.schema.events import EventType

from ._fake_file_executor import FakeFileExecutor

pytestmark = pytest.mark.postgres

_DRIVER = "tests.test_workflow.test_restart._restart_driver"


def _env(tmp_path: Path, wf_id: str, campaign_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env["FABERON_TEST_EXECUTOR_DIR"] = str(tmp_path / "executor")
    env["FABERON_TEST_RUN_DIR"] = str(tmp_path / "run")
    env["FABERON_TEST_WF_ID"] = wf_id
    env["FABERON_TEST_CAMPAIGN_ID"] = campaign_id
    return env


def _run(
    mode: str, env: dict[str, str], *, timeout: float = 30
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", _DRIVER, mode],
        env=env,
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_restart_after_kill(tmp_path):
    wf_id = f"exp-{int(time.time() * 1000)}"
    campaign_id = "88888888-4444-4444-4444-121212121212"
    env = _env(tmp_path, wf_id, campaign_id)

    # Metric output the parse step will read. 1.10 < baseline 1.23 -> keep.
    run_dir = Path(env["FABERON_TEST_RUN_DIR"])
    run_dir.mkdir()
    (run_dir / "metric.txt").write_text("val_bpb: 1.10\n")
    Path(env["FABERON_TEST_EXECUTOR_DIR"]).mkdir()

    executor = FakeFileExecutor(env["FABERON_TEST_EXECUTOR_DIR"])

    # Phase 1: start the control plane, let it submit, then kill it mid-poll.
    proc = subprocess.Popen(
        [sys.executable, "-m", _DRIVER, "start"],
        env=env,
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            if executor.submit_count() >= 1 and executor.job_id_for(wf_id):
                break
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                pytest.fail(f"start exited early:\n{err}")
            time.sleep(0.05)
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert executor.submit_count() == 1, "job was not submitted before kill"
    job_id = executor.job_id_for(wf_id)
    assert job_id is not None

    # Phase 2: mark the job complete, then restart a fresh process to recover.
    executor.complete(job_id, exit_code=0)
    result = _run("recover", env, timeout=30)
    assert result.returncode == 0, (
        f"recover failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "RESULT: keep" in result.stdout, (
        f"unexpected judgment:\n{result.stdout}\n{result.stderr}"
    )

    # Exactly once: one submitted (implicit), one completed, one judged.
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail())
    ledger.close()
    types = [e.type for e in events]
    assert types.count(EventType.EXPERIMENT_COMPLETED) == 1
    assert types.count(EventType.EXPERIMENT_JUDGED) == 1

    # The recovering process must not have resubmitted.
    assert executor.submit_count() == 1
