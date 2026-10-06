"""Shared test fakes."""

import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from faberon.executor import JobInfo, JobState, SubmitRequest
from faberon.schema import Event, ResearchPlan
from faberon.workflow.models import Proposal

_STATE_FILE = "executor_state.json"


class FakeEvents:
    """In-memory campaign event reader."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self.events = events or []

    def campaign_events(self, campaign_id: UUID) -> list[Event]:
        return [event for event in self.events if event.campaign_id == campaign_id]


class FakeProposer:
    """Deterministic proposer for campaign and API tests."""

    def __init__(self) -> None:
        self.proposal_count = 0

    def propose(
        self,
        campaign_id: UUID,
        plan: ResearchPlan,
        current_content: str,
    ) -> Proposal:
        self.proposal_count += 1
        return Proposal(
            content=current_content + f"# experiment {self.proposal_count}\n",
            title=f"test proposal {self.proposal_count}",
            rationale=f"rationale for test proposal {self.proposal_count}",
        )

    def close(self) -> None:
        """No-op stand-in for ``AgentProposer.close``"""


class FakeExecutor:
    """In-memory executor: fixed status on first poll, counts submissions."""

    def __init__(
        self,
        state: JobState = JobState.COMPLETED,
        *,
        exit_code: int | None = 0,
        elapsed_seconds: float = 60.0,
    ) -> None:
        self._state = state
        self._exit_code = exit_code
        self._elapsed_seconds = elapsed_seconds
        self.submit_count = 0

    def submit(self, request: SubmitRequest) -> str:
        self.submit_count += 1
        # Create a dummy stdout/stderr file if a test didn't pre-write one.
        out = Path(request.output_path)
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("")
        return f"fake-{self.submit_count}"

    def status(self, job_id: str) -> JobInfo:
        elapsed = self._elapsed_seconds if self._state.is_terminal else None
        return JobInfo(
            job_id=job_id,
            state=self._state,
            exit_code=self._exit_code,
            elapsed_seconds=elapsed,
        )

    def cancel(self, job_id: str) -> None:
        pass


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
        state_val = JobState(job["state"])
        return JobInfo(
            job_id=job_id,
            state=state_val,
            exit_code=job["exit_code"],
            elapsed_seconds=1.0 if state_val.is_terminal else None,
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
