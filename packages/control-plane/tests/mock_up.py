"""In-memory mock-ups for testing."""


from faberon.executor import JobInfo, JobState, SubmitRequest


class InMemoryExecutor:
    """In-memory executor for tests."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobInfo] = {}
        self._by_submission_key: dict[str, str] = {}
        self._next_id = 1

    def submit(self, request: SubmitRequest) -> str:
        existing = self._by_submission_key.get(request.submission_key)
        if existing is not None:
            return existing

        job_id = f"fake-{self._next_id}"
        self._next_id += 1
        self._by_submission_key[request.submission_key] = job_id
        self._jobs[job_id] = JobInfo(job_id=job_id, state=JobState.RUNNING)
        return job_id

    def status(self, job_id: str) -> JobInfo:
        return self._jobs[job_id]

    def cancel(self, job_id: str) -> None:
        job = self.status(job_id)
        if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            return
        self._jobs[job_id] = job.model_copy(update={"state": JobState.CANCELLED})

    def complete(self, job_id: str, *, exit_code: int = 0) -> None:
        """Test helper: mark a running job finished."""
        job = self.status(job_id)
        state = JobState.COMPLETED if exit_code == 0 else JobState.FAILED
        self._jobs[job_id] = job.model_copy(update={"state": state, "exit_code": exit_code})
