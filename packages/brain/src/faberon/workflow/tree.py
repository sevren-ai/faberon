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
