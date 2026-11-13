"""Tests against a throwaway git repo."""

import subprocess
from pathlib import Path

import pytest

from faberon.workflow import tree

from ..conftest import make_repo

_BASELINE_EXPERIMENT = "baseline"


def _git(repo: Path, *args: str) -> str:
    """Separate helper for tests to avoid using the production private copy"""
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _head(repo: Path) -> str:
    return tree.current_head(repo)


def test_commit_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    baseline_sha = _head(repo)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment A\n")
    result = tree.commit_file(repo, "train.py", "A fine experiment")
    assert result.sha == _head(repo)
    assert result.parent_sha == baseline_sha
    assert result.sha != baseline_sha


def test_commit_file_errors(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    with pytest.raises(RuntimeError):
        tree.commit_file(repo, "train.py", "no change")

    with pytest.raises(RuntimeError):
        tree.commit_file(repo, "missing.py", "super interesting missing file")


def test_discard(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment S\n")
    result = tree.commit_file(repo, "train.py", "Some experiment")
    assert _BASELINE_EXPERIMENT not in train_loc.read_text()

    tree.reset_hard(repo, result.parent_sha)
    assert _head(repo) == result.parent_sha
    assert _BASELINE_EXPERIMENT in train_loc.read_text()


def test_keep_continue(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment 1\n")
    kept = tree.commit_file(repo, "train.py", "My first experiment")

    train_loc.write_text("experiment 2\n")
    second = tree.commit_file(repo, "train.py", "My second experiment")

    assert second.parent_sha == kept.sha


def test_discard_continue(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
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


def test_discard_uncommitted_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    train_loc = repo / "train.py"
    train_loc.write_text("experiment 1\n")
    result = tree.commit_file(repo, "train.py", "My first experiment")
    train_loc.write_text("uncommitted mess\n")

    assert _BASELINE_EXPERIMENT not in train_loc.read_text()
    tree.reset_hard(repo, result.parent_sha)
    assert _BASELINE_EXPERIMENT in train_loc.read_text()


def test_uncommitted_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    assert tree.uncommitted_changes(repo) == []

    # Untracked files do not count.
    (repo / "notes.txt").write_text("scratch\n")
    assert tree.uncommitted_changes(repo) == []

    # Modified and staged tracked files do.
    (repo / "train.py").write_text("work in progress\n")
    assert tree.uncommitted_changes(repo) == ["train.py"]
    _git(repo, "add", "train.py")
    assert tree.uncommitted_changes(repo) == ["train.py"]


def test_branch_helpers(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, _BASELINE_EXPERIMENT)
    head = _head(repo)
    assert tree.branch_exists(repo, "main")
    assert not tree.branch_exists(repo, "work")
    assert tree.branch_tip(repo, "main") == head

    tree.create_branch(repo, "work", head)
    assert tree.branch_exists(repo, "work")
    assert tree.branch_tip(repo, "work") == head
    # Creating a branch does not move HEAD.
    assert tree.current_branch(repo) == "main"

    tree.checkout(repo, "work")
    assert tree.current_branch(repo) == "work"
    tree.checkout(repo, "main")
    assert tree.current_branch(repo) == "main"
