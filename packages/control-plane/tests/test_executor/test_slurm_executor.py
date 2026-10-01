"""Unit tests for the pure logic of faberon.executor.slurm.

These test module-level functions only: script rendering, sbatch command
construction, sacct parsing, and Slurm-state to JobState mapping. The
subprocess orchestration (which commands to call, idempotency lookup) is
not tested here; it is verified on-cluster by
test_slurm_integration.py.
"""

import pytest

from faberon.executor import JobState
from faberon.executor.protocol import JobInfo, SubmitRequest
from faberon.executor.slurm import (
    SlurmExecutor,
    _map_state,
    _parse_exit_code,
    _parse_sacct_line,
    _render_sbatch,
    _render_script,
)


def test_render_script():
    script = _render_script(["echo", "a b", "$X"])
    assert script.startswith("#!/bin/sh\nset -eu\nexec ")
    assert "echo 'a b' '$X'" in script


def test_render_sbatch():
    args = _render_sbatch(
        "faberon:exp-1",
        "minerva",
        ["uv", "run", "train.py"],
        time_limit=240,
    )
    assert args[0] == "sbatch"
    assert args[1:7] == [
        "--parsable",
        "--account=minerva",
        "--job-name=faberon:exp-1",
        "--gres=gpu:1",
        "--time=240",
        "--wrap",
    ]
    assert args[7] == _render_script(["uv", "run", "train.py"])


@pytest.mark.parametrize(
    "walltime,max_walltime,expected",
    [
        (120, None, 120),  # no cap set: request passes through
        (60, 240, 60),  # under the cap: unchanged
        (240, 120, 120),  # over the cap: clamped
        (120, 120, 120),  # exactly at the cap: unchanged
        (1, 1, 1),  # smallest valid values
    ],
)
def test_effective_walltime(walltime, max_walltime, expected):
    executor = SlurmExecutor("minerva", max_walltime=max_walltime)
    request = SubmitRequest(command="echo hello", submission_key="k", walltime=walltime)
    assert executor._effective_walltime(request) == expected


def test_effective_walltime_no_cap():
    executor = SlurmExecutor("minerva")
    request = SubmitRequest(command="echo hello", submission_key="k", walltime=90)
    assert executor._effective_walltime(request) == 90


@pytest.mark.parametrize(
    "exit_string,expected",
    [
        ("0:0", 0),
        ("2:0", 2),
        ("0:9", 0),
        ("", None),
        ("abc:0", None),
    ],
)
def test_parse_exit_code(exit_string, expected):
    assert _parse_exit_code(exit_string) == expected


@pytest.mark.parametrize(
    "line,expected",
    [
        ("COMPLETED|0:0|90", ("COMPLETED", "0:0", "90")),
        ("FAILED|2:0|5", ("FAILED", "2:0", "5")),
        (
            "CANCELLED by 1807600296|0:0|3723",
            ("CANCELLED by 1807600296", "0:0", "3723"),
        ),
    ],
)
def test_parse_sacct_line(line, expected):
    assert _parse_sacct_line(line) == expected


@pytest.mark.parametrize(
    "slurm_state,exit_string,expected_state,expected_exit",
    [
        ("COMPLETED", "0:0", JobState.COMPLETED, 0),
        ("FAILED", "2:0", JobState.FAILED, 2),
        ("CANCELLED", "0:0", JobState.CANCELLED, None),
        ("CANCELLED by 1807600296", "0:0", JobState.CANCELLED, None),
        ("TIMEOUT", "0:0", JobState.FAILED, 0),
        ("OUT_OF_MEMORY", "0:0", JobState.FAILED, 0),
        ("RUNNING", "0:0", JobState.RUNNING, None),
        ("PENDING", "0:0", JobState.RUNNING, None),
        ("PREEMPTED", "0:0", JobState.RUNNING, None),
    ],
)
def test_map_state(slurm_state, exit_string, expected_state, expected_exit):
    assert _map_state(slurm_state, exit_string, 60.0) == (
        expected_state,
        expected_exit,
        60.0 if expected_state != JobState.RUNNING else None,
    )


def test_map_state_unknown_raises():
    with pytest.raises(ValueError):
        _map_state("UNKNOWN_ISSUE", "0:0")


def test_jobinfo_terminal_requires_elapsed():
    with pytest.raises(ValueError, match="elapsed_seconds"):
        JobInfo(job_id="j1", state=JobState.COMPLETED, elapsed_seconds=None)


def test_jobinfo_running_allows_no_elapsed():
    info = JobInfo(job_id="j1", state=JobState.RUNNING, elapsed_seconds=None)
    assert info.elapsed_seconds is None
