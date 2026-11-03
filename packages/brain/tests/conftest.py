"""Shared pytest hooks and fixtures for the brain test suite."""

import os
import subprocess
import tempfile
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from faberon import config
from faberon.schema import ResearchPlan

TEST_DB_NAME = "faberon_test"


def _test_db_url(base: str) -> str:
    """The base database URL with the database part swapped for the test database."""
    try:
        url = make_url(base)
    except ArgumentError:
        return ""
    return url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)


def _ensure_test_db(test_url: str) -> str:
    """Create the test database if needed; '' on success, else the reason."""
    maintenance = (
        make_url(test_url)
        .set(database="postgres")
        .render_as_string(hide_password=False)
    )
    try:
        with psycopg.connect(maintenance, connect_timeout=2, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    except psycopg.OperationalError:
        return f"no Postgres at {maintenance}: start it first"
    except psycopg.Error as exc:
        return f"could not create the {TEST_DB_NAME} database: {exc}"
    return ""


# Why postgres-marked tests skip this run; empty when the test DB is ready.
_postgres_note = ""
# The generated config's database URL, kept for the skip logic. Tests that
# open a Ledger or DBOS directly read it via config.database_url().
_test_url = ""


def pytest_configure() -> None:
    """Point the whole run at a generated config file using the test database."""
    global _postgres_note, _test_url
    real = config.load()
    test_url = _test_db_url(real.get("database_url", "postgres:///faberon"))
    values = {key: real[key] for key in ("model", "slurm_account") if real.get(key)}
    if test_url:
        values["database_url"] = test_url
    # The generated config must be complete, as serve demands.
    completing = {
        "host": config.DEFAULT_HOST,
        "port": config.DEFAULT_PORT,
        "proposer_timeout": config.DEFAULT_PROPOSER_TIMEOUT,
        "state_dir": config.DEFAULT_STATE_DIR,
    }
    for key, default in completing.items():
        values[key] = real.get(key) or default
    path = Path(tempfile.mkdtemp(prefix="faberon-test-")) / "config.toml"
    config.write(path, values, dict(real.get("env", {})))
    os.environ["FABERON_CONFIG"] = str(path)
    if test_url:
        _test_url = test_url
        _postgres_note = _ensure_test_db(test_url)


def _postgres_is_reachable(url: str) -> bool:
    try:
        conn = psycopg.connect(url, connect_timeout=2)
        conn.close()
        return True
    except psycopg.OperationalError:
        return False


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip tests whose infrastructure is not configured or reachable."""
    if "postgres" in item.keywords:
        if not _test_url or _postgres_note or not _postgres_is_reachable(_test_url):
            reason = _postgres_note or f"no Postgres at {_test_url}: start it first"
            pytest.skip(reason)
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not config.slurm_account():
            pytest.skip("no slurm_account in the config file: run `faberon init`")
    if "llm" in item.keywords:
        if not config.model():
            pytest.skip("no model in the config file: run `faberon init`")


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
        "command": "echo hello",
        "target_file": "train.py",
        "metric": "val_bpb",
        "baseline": 1.23,
        "budget_gpu_hours": 100.0,
        "max_experiments": 3,
        "max_concurrency": 1,
        "walltime": 10,
        "stop_conditions": ["n/a"],
    }
    data.update(overrides)
    return ResearchPlan.model_validate(data)
