"""Local executor: run jobs as subprocesses on the machine hosting Faberon.

The executor keeps a job registry: one JSON record per job (``{job_id}.json``).
This lets the executor survive a brain restart.
"""

import fcntl
import json
import logging
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from .protocol import JobInfo, JobState, SubmitRequest

_JOB_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_WAIT_EXIT_TIMEOUT_S = 1.0

logger = logging.getLogger(__name__)


def _sanitize_job_id(job_id: str) -> str:
    return _JOB_ID_SAFE.sub("_", job_id)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process exists but is owned by another user; not our job.
        return False
    return True


def _read_record(path: Path) -> dict[str, Any] | None:
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        return None
    except json.JSONDecodeError:
        logger.warning("corrupt local job record: %s", path)
        return None


class LocalExecutor:
    """Executor that runs each experiment as a local subprocess."""

    def __init__(
        self, state_dir: str | Path, *, max_walltime: int | None = None
    ) -> None:
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_walltime = max_walltime

    def _effective_walltime(self, request: SubmitRequest) -> int:
        """Clamp the request's walltime to the deployment-side cap, if set."""
        if self._max_walltime is None:
            return request.walltime
        return min(request.walltime, self._max_walltime)

    def submit(self, request: SubmitRequest) -> str:
        """Start the job, or return the existing id for a duplicate key."""
        job_id = _sanitize_job_id(request.submission_key)
        path = self._record_path(job_id)

        # Serialize submitters so two concurrent submits of the same key
        # cannot both spawn a process.
        lock = open(self._dir / ".lock", "a+b")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            existing = _read_record(path)
            if existing is not None:
                return job_id
            record = self._spawn(job_id, request)
            self._write_record(path, record)
            return job_id
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def status(self, job_id: str) -> JobInfo:
        record = _read_record(self._record_path(job_id))
        if record is None:
            raise KeyError(job_id)
        return self._refresh(record)

    def cancel(self, job_id: str) -> None:
        record = _read_record(self._record_path(job_id))
        if record is None:
            return
        pid = record.get("pid")
        if record.get("exit_code") is None and pid is not None:
            if _pid_alive(pid):
                os.kill(pid, signal.SIGTERM)
                record = self._settle(record, cancelled=True)
        if record.get("exit_code") is not None:
            return
        raise RuntimeError(f"local job {job_id} still running after cancel")

    # Internal helpers -------------------------------------------------

    def _record_path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.json"

    def _spawn(self, job_id: str, request: SubmitRequest) -> dict[str, Any]:
        stdout_path = Path(request.output_path)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        # Line buffering keeps the metric output file current for a metric
        # command that reads it while the job runs. Own process group so
        # cancel/timeout can signal the whole tree.
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        with open(stdout_path, "wb") as stdout:
            proc = subprocess.Popen(
                request.argv,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
        return {
            "job_id": job_id,
            "submission_key": request.submission_key,
            "pid": proc.pid,
            "start_time": start,
            "deadline": start + self._effective_walltime(request) * 60,
            "exit_code": None,
            "cancelled": False,
        }

    def _refresh(self, record: dict[str, Any]) -> JobInfo:
        """Reconcile a running record with the live process, then to JobInfo."""
        if record.get("exit_code") is None:
            record = self._poll(record)
        return self._to_info(record)

    def _poll(self, record: dict[str, Any]) -> dict[str, Any]:
        """Advance a running record: harvest exit, enforce walltime."""
        pid = record["pid"]
        rc = _wait_pid(pid, timeout=0.0)
        if rc is not None:
            return self._finalize(record, rc)
        if time.monotonic() >= record["deadline"]:
            os.kill(pid, signal.SIGKILL)
            return self._settle(record, cancelled=False)
        return record

    def _settle(self, record: dict[str, Any], *, cancelled: bool) -> dict[str, Any]:
        """Reap a process we just signalled and finalize its record."""
        record = dict(record)
        record["cancelled"] = cancelled
        rc = _wait_pid(record["pid"], timeout=_WAIT_EXIT_TIMEOUT_S)
        return self._finalize(record, rc)

    def _finalize(
        self, record: dict[str, Any], exit_code: int | None
    ) -> dict[str, Any]:
        record = dict(record)
        record["exit_code"] = exit_code
        record["end_time"] = time.time()
        self._write_record(self._record_path(record["job_id"]), record)
        return record

    def _to_info(self, record: dict[str, Any]) -> JobInfo:
        job_id = record["job_id"]
        exit_code = record.get("exit_code")
        if exit_code is None:
            return JobInfo(job_id=job_id, state=JobState.RUNNING, exit_code=None)
        elapsed = record["end_time"] - record["start_time"]
        if record.get("cancelled"):
            return JobInfo(
                job_id=job_id,
                state=JobState.CANCELLED,
                exit_code=None,
                elapsed_seconds=elapsed,
            )
        state = JobState.COMPLETED if exit_code == 0 else JobState.FAILED
        return JobInfo(
            job_id=job_id, state=state, exit_code=exit_code, elapsed_seconds=elapsed
        )

    def _write_record(self, path: Path, record: dict[str, Any]) -> None:
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(record, f)
        os.replace(tmp, path)


def _wait_pid(pid: int, timeout: float) -> int | None:
    """Wait for a child pid, returning its exit code, or None if still running.

    Returns 0 when the process is gone but no longer waitable (already reaped
    by a prior wait, or not our child), since its true code is unrecoverable.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return 0
        if wpid == pid:
            return _status_to_exit_code(status)
        if not _pid_alive(pid):
            # Gone but not waitable (e.g. reaped elsewhere).
            return 0
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.01)


def _status_to_exit_code(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 0
