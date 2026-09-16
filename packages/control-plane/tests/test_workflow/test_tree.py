"""Tests against a throwaway git repo."""

import subprocess
from pathlib import Path

import pytest

from faberon.workflow import tree

_BASELINE_EXPERIMENT = "baseline"


def _git(repo: Path, *args: str) -> str:
    """Separate helper for tests to avoid using the production private copy"""
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one baseline commit containing train.py."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "smith@forge.com")
    _git(tmp_path, "config", "user.name", "Black")
    train_loc = tmp_path / "train.py"
    train_loc.write_text(f"{_BASELINE_EXPERIMENT}\n")
    _git(tmp_path, "add", "train.py")
    _git(tmp_path, "commit", "-m", "My beautiful baseline")
    return tmp_path


def _head(repo: Path) -> str:
    return tree.current_head(repo)


def test_commit_file(repo: Path) -> None:
    baseline_sha = _head(repo)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment A\n")
    result = tree.commit_file(repo, "train.py", "A fine experiment")
    assert result.sha == _head(repo)
    assert result.parent_sha == baseline_sha
    assert result.sha != baseline_sha


def test_commit_file_errors(repo: Path) -> None:
    with pytest.raises(RuntimeError):
        tree.commit_file(repo, "train.py", "no change")

    with pytest.raises(RuntimeError):
        tree.commit_file(repo, "missing.py", "super interesting missing file")


def test_discard(repo: Path) -> None:
    train_loc = repo / "train.py"
    train_loc.write_text("experiment S\n")
    result = tree.commit_file(repo, "train.py", "Some experiment")
    assert _BASELINE_EXPERIMENT not in train_loc.read_text()

    tree.reset_hard(repo, result.parent_sha)
    assert _head(repo) == result.parent_sha
    assert _BASELINE_EXPERIMENT in train_loc.read_text()


def test_keep_continue(repo: Path) -> None:
    train_loc = repo / "train.py"
    train_loc.write_text("experiment 1\n")
    kept = tree.commit_file(repo, "train.py", "My first experiment")

    train_loc.write_text("experiment 2\n")
    second = tree.commit_file(repo, "train.py", "My second experiment")

    assert second.parent_sha == kept.sha


def test_discard_continue(repo: Path) -> None:
    baseline_sha = _head(repo)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment 1\n")
    discarded = tree.commit_file(repo, "train.py", "My first experiment")
    tree.reset_hard(repo, discarded.parent_sha)

    train_loc.write_text("experiment 2\n")
    second = tree.commit_file(repo, "train.py", "My second experiment")

    assert second.parent_sha == baseline_sha
    assert discarded.sha not in _git(repo, "log", "--format=%H")
    # The dangling commit is still recoverable by sha
    assert _git(repo, "cat-file", "-t", discarded.sha) == "commit"


def test_discard_uncommitted_changes(repo: Path) -> None:
    train_loc = repo / "train.py"
    train_loc.write_text("experiment 1\n")
    result = tree.commit_file(repo, "train.py", "My first experiment")
    train_loc.write_text("uncommitted mess\n")

    assert _BASELINE_EXPERIMENT not in train_loc.read_text()
    tree.reset_hard(repo, result.parent_sha)
    assert _BASELINE_EXPERIMENT in train_loc.read_text()
