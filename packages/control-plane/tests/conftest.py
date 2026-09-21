"""Shared pytest hooks and fixtures for the control-plane test suite."""

import os
import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from faberon.schema.plan import ResearchPlan

TEST_DB_NAME = "faberon_test"


def _test_db_url() -> str:
    """FABERON_DATABASE_URL with the database part swapped for the test database."""
    base = os.environ.get("FABERON_DATABASE_URL", "")
    if not base:
        return ""
    try:
        parts = conninfo_to_dict(base)
    except psycopg.ProgrammingError:
        return ""
    parts["dbname"] = TEST_DB_NAME
    return make_conninfo(**{k: str(v) for k, v in parts.items() if v is not None})


def pytest_configure() -> None:
    """Redirect FABERON_DATABASE_URL to the test database for the whole run."""
    url = _test_db_url()
    if url:
        os.environ["FABERON_DATABASE_URL"] = url


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
            pytest.skip(
                f"no {TEST_DB_NAME} database at {url}: run scripts/create-faberon-db.sh"
            )
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not os.environ.get("FABERON_SLURM_ACCOUNT"):
            pytest.skip(
                "set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to"
            )
    if "llm" in item.keywords:
        if not os.environ.get("FABERON_MODEL"):
            pytest.skip("set FABERON_MODEL (and the provider key) to run LLM tests")


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
