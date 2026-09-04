"""Unit tests for the pure logic of faberon.executor.slurm.

These test module-level functions only: script rendering, sbatch command
construction, sacct parsing, and Slurm-state to JobState mapping. The
subprocess orchestration (which commands to call, idempotency lookup) is
not tested here; it is verified on-cluster by
test_slurm_integration.py.
"""

import pytest

from faberon.executor import JobState
from faberon.executor.slurm import (
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
    args = _render_sbatch("faberon:exp-1", "minerva", ["uv", "run", "train.py"])
    assert args[0] == "sbatch"
    assert args[1:5] == [
        "--parsable",
        "--account=minerva",
        "--job-name=faberon:exp-1",
        "--wrap",
    ]
    assert args[5] == _render_script(["uv", "run", "train.py"])


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
        ("COMPLETED|0:0", ("COMPLETED", "0:0")),
        ("FAILED|2:0", ("FAILED", "2:0")),
        ("CANCELLED by 1807600296|0:0", ("CANCELLED by 1807600296", "0:0")),
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
    assert _map_state(slurm_state, exit_string) == (expected_state, expected_exit)


def test_map_state_unknown_raises():
    with pytest.raises(ValueError):
        _map_state("UNKNOWN_ISSUE", "0:0")
