"""Durable experiment workflow: submit, poll, parse, judge, record."""

import os
import re
from pathlib import Path

from dbos import DBOS

from ..executor import Executor, JobInfo, JobState, SubmitRequest
from ..ledger import Ledger
from ..schema.events import Actor, Event, EventType
from .models import ExperimentResult, ExperimentSetup


@DBOS.dbos_class()
class Runtime:
    """Owns the executor, the ledger, and the durable experiment workflow.

    Construct one at process startup, register it with
    `DBOS.register_instance`, then `DBOS.launch()`.
    `config_name` uniquely identifies the instance for workflow recovery.
    """

    def __init__(self, executor: Executor, ledger: Ledger, config_name: str) -> None:
        self.executor = executor
        self.ledger = ledger
        self.config_name = config_name

    @DBOS.step()
    def submit_step(
        self, command: str, submission_key: str, walltime: int, repo_path: str
    ) -> str:
        """Start the job on the cluster. Idempotent on submission_key."""
        output_path = _job_log_path(repo_path, submission_key)
        _private_dir(output_path.parent)
        request = SubmitRequest(
            command=command,
            submission_key=submission_key,
            walltime=walltime,
            output_path=str(output_path),
        )
        return self.executor.submit(request)

    @DBOS.step()
    def status_step(self, job_id: str) -> JobInfo:
        """Read the current status of the job from the cluster."""
        return self.executor.status(job_id)

    @DBOS.step()
    def parse_metric_step(
        self, repo_path: str, submission_key: str, metric_name: str
    ) -> float | None:
        """Read the job's log and parse the metric value.

        Returns None if the log is missing or no float could be parsed. The
        log is expected to print a line containing the metric name followed
        by a float, for example `val_bpb: 1.10`.
        """
        log = _job_log_path(repo_path, submission_key)
        try:
            stdout = log.read_text()
        except OSError:
            return None
        return _parse_metric(stdout, metric_name)

    @DBOS.step()
    def judge_step(
        self, metric_value: float | None, baseline: float, info: JobInfo
    ) -> tuple[str, str]:
        """Apply a simple keep/discard rule: lower is better (keep)."""
        if info.state != JobState.COMPLETED:
            return "discard", f"job {info.state.value}"
        if info.exit_code != 0:
            return "discard", f"job exit {info.exit_code}"
        if metric_value is None:
            return "discard", "metric unparseable"
        if metric_value < baseline:
            return "keep", f"metric {metric_value} beats best {baseline}"
        return "discard", f"metric {metric_value} does not beat best {baseline}"

    @DBOS.transaction()
    def record_event_step(self, event: Event) -> int:
        """Append one event to the ledger. Exactly-once via DBOS transaction."""
        return self.ledger.append_with_session(DBOS.sql_session, event)

    @DBOS.workflow()
    def run_experiment(self, setup: ExperimentSetup) -> ExperimentResult:
        """Run one experiment durably: submit, poll, parse, judge, record."""
        job_id = self.submit_step(
            setup.command, setup.submission_key, setup.walltime, setup.repo_path
        )
        self.record_event_step(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_SUBMITTED,
                reason=f"job {job_id} submitted",
                payload={
                    "job_id": job_id,
                    "index": setup.index,
                    "sha": setup.sha,
                    "command": setup.command,
                },
            )
        )

        info = self.status_step(job_id)
        while not info.state.is_terminal:
            DBOS.sleep(setup.poll_interval_seconds)
            info = self.status_step(job_id)

        metric_value: float | None = None
        if info.state == JobState.COMPLETED and info.exit_code == 0:
            metric_value = self.parse_metric_step(
                setup.repo_path, setup.submission_key, setup.metric
            )

        judgment, reason = self.judge_step(metric_value, setup.baseline, info)
        exit_code_str = str(info.exit_code) if info.exit_code is not None else "n/a"
        metric_value_str = str(metric_value) if metric_value is not None else "n/a"

        self.record_event_step(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_COMPLETED,
                reason=f"job {job_id} {info.state.value} exit={exit_code_str}",
                payload={
                    "job_id": job_id,
                    "index": setup.index,
                    "sha": setup.sha,
                    "command": setup.command,
                    "state": info.state.value,
                    "exit_code": info.exit_code,
                    "elapsed_seconds": info.elapsed_seconds,
                },
            )
        )
        self.record_event_step(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_JUDGED,
                reason=(
                    f"metric={metric_value_str} baseline={setup.baseline} "
                    f"judgment={judgment}"
                ),
                payload={
                    "job_id": job_id,
                    "index": setup.index,
                    "sha": setup.sha,
                    "metric_value": metric_value,
                    "baseline": setup.baseline,
                    "judgment": judgment,
                    "reason": reason,
                },
            )
        )
        return ExperimentResult(
            judgment=judgment, metric_value=metric_value, job_info=info
        )


def _job_log_path(repo_path: str, submission_key: str) -> Path:
    """The job's log file: ``{repo}/.faberon/{submission_key}.out``.

    The metric command reads this file, so the path is stable and derived
    from the target repo, not from global config.
    """
    return Path(repo_path) / ".faberon" / f"{submission_key}.out"


def _private_dir(path: Path) -> None:
    """Create a directory readable only by its owner."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


# -XXX.YYe-Z
_FLOAT_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def _parse_metric(stdout: str, metric_name: str) -> float | None:
    """Return the last float on the last line that names the metric.

    Returns None if no line names the metric or no float is on it.
    """
    for line in reversed(stdout.splitlines()):
        if metric_name in line:
            nums = _FLOAT_RE.findall(line)
            if nums:
                return float(nums[-1])
    return None
