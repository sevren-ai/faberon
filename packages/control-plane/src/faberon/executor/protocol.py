"""Job executor contract: submit, poll status, cancel."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator


class JobState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset((JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED))


class SubmitRequest(BaseModel):
    """Request to start a job."""

    command: list[str] = Field(min_length=1)
    submission_key: str = Field(min_length=1)
    walltime: int = Field(gt=0)  # in minutes


class JobInfo(BaseModel):
    """All current info of a certain job."""

    job_id: str
    state: JobState
    exit_code: int | None = None
    elapsed_seconds: float | None = None

    @model_validator(mode="after")
    def _terminal_implies_elapsed(self) -> JobInfo:
        # terminal state should have elapsed_seconds set
        if self.state.is_terminal and self.elapsed_seconds is None:
            raise ValueError("elapsed_seconds is required on terminal jobs")
        return self


class Executor(Protocol):
    def submit(self, request: SubmitRequest) -> str:
        """Start a job. Returns a job id. Same submission_key returns the same id."""

    def status(self, job_id: str) -> JobInfo:
        """Return the current status of a job."""

    def cancel(self, job_id: str) -> None:
        """Cancel a job if it is still running."""
