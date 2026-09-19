"""Shared pytest hooks and fixtures for the control-plane test suite."""

import os
import subprocess
from pathlib import Path

import psycopg
import pytest

from faberon.schema.plan import ResearchPlan


def _postgres_is_reachable(url: str) -> bool:
    try:
        conn = psycopg.connect(url, connect_timeout=2)
        conn.close()
        return True
    except psycopg.OperationalError:
        return False


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip specific tests if the correct env vars are not set."""
    if "postgres" in item.keywords:
        url = os.environ.get("FABERON_DATABASE_URL")
        if not url:
            pytest.skip("set FABERON_DATABASE_URL to a Postgres instance")
        if not _postgres_is_reachable(url):
            pytest.skip(f"Postgres is not running at {url}.")
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not os.environ.get("FABERON_SLURM_ACCOUNT"):
            pytest.skip(
                "set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to"
            )


def _git(repo: Path, *args: str) -> str:
    """Run git in a test repo, asserting success."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def make_repo(tmp_path: Path, baseline: str = "baseline") -> Path:
    """Create a git repo at ``tmp_path/repo`` with one baseline commit of train.py."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "smith@forge.com")
    _git(repo, "config", "user.name", "Black")
    (repo / "train.py").write_text(f"{baseline}\n")
    _git(repo, "add", "train.py")
    _git(repo, "commit", "-m", "baseline")
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo at ``tmp_path/repo`` with one baseline commit of train.py."""
    return make_repo(tmp_path)


def make_plan(**overrides) -> ResearchPlan:
    """A valid research plan; tests override the fields they care about."""
    data = {
        "goal": "Beat val_bpb baseline.",
        "metric_name": "val_bpb",
        "metric_command": "cat metric.txt",
        "baseline": 1.23,
        "budget_gpu_hours": 100.0,
        "max_experiments": 3,
        "max_concurrency": 1,
        "walltime": 10,
        "stop_conditions": ["n/a"],
    }
    data.update(overrides)
    return ResearchPlan.model_validate(data)
