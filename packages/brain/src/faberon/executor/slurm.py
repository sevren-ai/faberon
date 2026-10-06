"""Slurm executor: real sbatch/sacct/scancel adapter."""

import shlex
import subprocess
from collections.abc import Sequence

from .protocol import JobInfo, JobState, SubmitRequest

# Prefix keeps Faberon job names apart from unrelated jobs on a shared cluster
JOB_NAME_PREFIX = "faberon:"

# Slurm states grouped by how they map onto JobState
_LIVE_STATES = {
    "PENDING",
    "RUNNING",
    "CONFIGURING",
    "COMPLETING",
    "REQUEUED",
    "PREEMPTED",  # preempted jobs are requeued, so still live
}
_CANCELLED_STATES = {"CANCELLED", "REVOKED"}
_FAILED_STATES = {
    "FAILED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "BOOT_FAIL",
    "DEADLINE",
}


def _render_script(command: Sequence[str]) -> str:
    script = "#!/bin/sh\n"
    script += "set -eu\n"  # fail loudly & early

    quoted = " ".join(shlex.quote(a) for a in command)
    script += "exec " + quoted + "\n"
    return script


def _render_sbatch(
    job_name: str,
    account: str,
    command: Sequence[str],
    *,
    output: str | None = None,
    gpus: int = 1,
    time_limit: int,
) -> list[str]:
    args = [
        "sbatch",
        "--parsable",
        f"--account={account}",
        f"--job-name={job_name}",
        f"--gres=gpu:{gpus}",
        f"--time={time_limit}",
    ]
    if output is not None:
        args.append(f"--output={output}")
    args += ["--wrap", _render_script(command)]
    return args


def _parse_exit_code(exit_string: str) -> int | None:
    # expected exit_string is something like "exitcode:signal"
    try:
        return int(exit_string.split(":", 1)[0])
    except ValueError:
        return None


def _parse_sacct_line(line: str) -> tuple[str, str, str]:
    # expecting something like "state|exitcode:signal|elapsed_raw_seconds"
    fields = line.split("|", 2)
    assert len(fields) == 3
    return fields[0], fields[1], fields[2]


def _map_state(
    slurm_state: str,
    exit_string: str,
    elapsed_seconds: float | None = None,
) -> tuple[JobState, int | None, float | None]:
    """Map a sacct line to JobState, exit code, and elapsed seconds."""
    # Match by substring
    exit_code = _parse_exit_code(exit_string)
    if any(s in slurm_state for s in _CANCELLED_STATES):
        # cancelled: no meaningful app exit code
        return JobState.CANCELLED, None, elapsed_seconds
    if "COMPLETED" in slurm_state:
        code = exit_code if exit_code is not None else 0
        return JobState.COMPLETED, code, elapsed_seconds
    if any(s in slurm_state for s in _LIVE_STATES):
        # live jobs have no final elapsed yet
        return JobState.RUNNING, None, None
    if any(s in slurm_state for s in _FAILED_STATES):
        return JobState.FAILED, exit_code, elapsed_seconds
    raise ValueError(f"unrecognized Slurm state: {slurm_state!r}")


class SlurmExecutor:
    """Executor backed by a local Slurm install.

    Runs on the login node, where sbatch/sacct/scancel are local subprocesses.
    Job state lives in Slurm, so submission_key idempotency survives restarts.
    """

    def __init__(
        self,
        account: str,
        *,
        gpus: int = 1,
        max_walltime: int | None = None,
    ) -> None:
        self._account = account
        self._gpus = gpus
        self._max_walltime = max_walltime

    def _effective_walltime(self, request: SubmitRequest) -> int:
        """Clamp the request's walltime to the deployment-side cap, if set."""
        if self._max_walltime is None:
            return request.walltime
        return min(request.walltime, self._max_walltime)

    def submit(self, request: SubmitRequest) -> str:
        job_name = JOB_NAME_PREFIX + request.submission_key
        existing = self._find_job_by_name(job_name)
        if existing is not None:
            return existing
        result = subprocess.run(
            _render_sbatch(
                job_name,
                self._account,
                request.argv,
                output=request.output_path,
                gpus=self._gpus,
                time_limit=self._effective_walltime(request),
            ),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "sbatch failed")
        job_id = result.stdout.strip()
        if not job_id:
            raise RuntimeError("sbatch returned no job id")
        return job_id

    def status(self, job_id: str) -> JobInfo:
        live = self._squeue_state(job_id)
        if live is not None:
            return live
        return self._sacct_state(job_id)

    def cancel(self, job_id: str) -> None:
        result = subprocess.run(["scancel", job_id], capture_output=True, text=True)
        if result.returncode == 0:
            return
        # Nonzero usually means the job already finished. Confirm via status;
        # if it is still live, the cancel genuinely failed.
        try:
            info = self.status(job_id)
        except KeyError:
            return
        if info.state == JobState.RUNNING:
            raise RuntimeError(result.stderr.strip() or "scancel failed")

    def _find_job_by_name(self, job_name: str) -> str | None:
        # Live jobs first (squeue), then completed (sacct).
        result = subprocess.run(
            ["squeue", "-h", "--name", job_name, "-o", "%i"],
            capture_output=True,
            text=True,
        )
        live = result.stdout.split()
        if live:
            return live[0]
        result = subprocess.run(
            ["sacct", "-X", "--name", job_name, "-P", "-o", "JobID", "-n"],
            capture_output=True,
            text=True,
        )
        done = result.stdout.split()
        if done:
            return done[0]
        return None

    def _squeue_state(self, job_id: str) -> JobInfo | None:
        result = subprocess.run(
            ["squeue", "-h", "-j", job_id, "-o", "%T"], capture_output=True, text=True
        )
        if not result.stdout.strip():
            return None
        return JobInfo(job_id=job_id, state=JobState.RUNNING, exit_code=None)

    def _sacct_state(self, job_id: str) -> JobInfo:
        result = subprocess.run(
            [
                "sacct",
                "-X",
                "-j",
                job_id,
                "-P",
                "-o",
                "State,ExitCode,ElapsedRaw",
                "-n",
            ],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        if not lines:
            raise KeyError(job_id)
        slurm_state, exit_string, elapsed_raw = _parse_sacct_line(lines[0])
        state, exit_code, elapsed_seconds = _map_state(
            slurm_state, exit_string, float(elapsed_raw)
        )
        return JobInfo(
            job_id=job_id,
            state=state,
            exit_code=exit_code,
            elapsed_seconds=elapsed_seconds,
        )
