"""File-backed executor for the restart test."""

import json
import os
import tempfile

from faberon.executor import JobInfo, JobState, SubmitRequest

_STATE_FILE = "executor_state.json"


class FakeFileExecutor:
    """Fake executor protocol backed by a JSON file. Test-only."""

    def __init__(self, dir_path: str) -> None:
        self._path = os.path.join(dir_path, _STATE_FILE)
        if not os.path.exists(self._path):
            self._save({"jobs": {}, "by_key": {}, "next_id": 1, "submit_count": 0})

    def submit(self, request: SubmitRequest) -> str:
        state = self._load()
        existing = state["by_key"].get(request.submission_key)
        if existing is not None:
            return existing
        job_id = f"fake-{state['next_id']}"
        state["next_id"] += 1
        state["submit_count"] += 1
        state["by_key"][request.submission_key] = job_id
        state["jobs"][job_id] = {"state": JobState.RUNNING.value, "exit_code": None}
        self._save(state)
        return job_id

    def status(self, job_id: str) -> JobInfo:
        state = self._load()
        job = state["jobs"][job_id]
        return JobInfo(
            job_id=job_id,
            state=JobState(job["state"]),
            exit_code=job["exit_code"],
        )

    def cancel(self, job_id: str) -> None:
        state = self._load()
        job = state["jobs"].get(job_id)
        if job is None:
            return
        if job["state"] == JobState.RUNNING.value:
            job["state"] = JobState.CANCELLED.value
            self._save(state)

    # Test helpers (called by the parent process, not by the workflow).

    def complete(self, job_id: str, *, exit_code: int = 0) -> None:
        state = self._load()
        job = state["jobs"][job_id]
        state_val = JobState.COMPLETED if exit_code == 0 else JobState.FAILED
        job["state"] = state_val.value
        job["exit_code"] = exit_code
        self._save(state)

    def submit_count(self) -> int:
        return self._load()["submit_count"]

    def job_id_for(self, submission_key: str) -> str | None:
        return self._load()["by_key"].get(submission_key)

    def _load(self) -> dict:
        with open(self._path) as f:
            return json.load(f)

    def _save(self, state: dict) -> None:
        # Atomic write so readers never see a half-written file.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self._path))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp, self._path)
        except Exception:
            os.unlink(tmp)
            raise
