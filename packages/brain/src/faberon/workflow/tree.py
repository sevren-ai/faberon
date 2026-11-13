"""Experiment tree: commit and reset operations on the target repo.

One experiment is one commit. ``commit_file`` records sha and parent sha in
the ledger; discard is ``reset_hard`` to the parent, leaving the commit
dangling but recoverable by sha. Assumes sequential checkouts.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommitResult:
    """The experiment commit and its parent."""

    sha: str
    parent_sha: str


def _run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def current_head(repo: Path) -> str:
    """Return the full sha of the current head commit."""
    return _run(repo, "rev-parse", "HEAD")


def current_branch(repo: Path) -> str | None:
    """Return the current branch name, or None on a detached HEAD."""
    result = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "-q", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise RuntimeError(f"git symbolic-ref failed: {result.stderr.strip()}")
    return result.stdout.strip()


def uncommitted_changes(repo: Path) -> list[str]:
    """Return tracked files with uncommited changes"""
    out = _run(repo, "diff", "--name-only", "HEAD", "--")
    return out.splitlines()


def branch_exists(repo: Path, name: str) -> bool:
    """Return whether the repo has a local branch with that name."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{name}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(f"git rev-parse failed: {result.stderr.strip()}")


def branch_tip(repo: Path, name: str) -> str:
    """Return the full sha of the branch's tip commit."""
    return _run(repo, "rev-parse", f"refs/heads/{name}")


def create_branch(repo: Path, name: str, sha: str) -> None:
    """Create a branch pointing at the given commit."""
    _run(repo, "branch", name, sha)


def checkout(repo: Path, branch: str) -> None:
    """Switch the working tree to the given branch."""
    _run(repo, "checkout", branch)


def commit_file(repo: Path, path: str, message: str) -> CommitResult:
    """Stage and commit one file on top of the current head.

    Conditions (error is raised if not fulfilled):
      - The repo must already contain one commit
      - The given file exists
      - The given file differs from the head's version
    """
    parent_sha = current_head(repo)
    _run(repo, "add", path)
    _run(repo, "commit", "-m", message)
    return CommitResult(sha=current_head(repo), parent_sha=parent_sha)


def reset_hard(repo: Path, sha: str) -> None:
    """Move the branch to sha and restore the working tree to match."""
    _run(repo, "reset", "--hard", sha)
