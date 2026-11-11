"""Shared pytest hooks and fixtures for the brain test suite."""

import os
import shutil
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

# The test database name can never collide with the maintenance
# database or the production default. Everything below relies on it.
assert TEST_DB_NAME not in ("postgres", "faberon")


def _test_db_url(base: str) -> str:
    """The base database URL with the database part swapped for the test database.

    Empty when the base is unparseable or already points at the test
    database: that would mean the operator's own database is the one we
    drop, so the suite must refuse.
    """
    try:
        url = make_url(base)
    except ArgumentError:
        return ""
    if url.database == TEST_DB_NAME:
        return ""
    return url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)


def _ensure_test_db(test_url: str) -> str:
    """Recreate the test database. Return '' on success, else the reason."""
    # Fail stop before any DROP; the URL must point at the test DB.
    assert make_url(test_url).database == TEST_DB_NAME
    maintenance = (
        make_url(test_url)
        .set(database="postgres")
        .render_as_string(hide_password=False)
    )
    try:
        with psycopg.connect(maintenance, connect_timeout=2, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
            conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    except psycopg.OperationalError:
        return f"no Postgres at {maintenance}: start it first"
    except psycopg.Error as exc:
        return f"could not (re)create the {TEST_DB_NAME} database: {exc}"
    return ""


# Why postgres-marked tests skip this run; empty when the test DB is ready.
_postgres_note = ""
# The generated config's database URL, kept for the skip logic. Tests that
# open a Ledger or DBOS directly read it via config.database_url().
_test_url = ""


def pytest_configure() -> None:
    """Point the run at a generated config using a freshly recreated test database."""
    global _postgres_note, _test_url
    real = config.load()
    base_url = real.get("database_url", "postgres:///faberon")
    test_url = _test_db_url(base_url)
    if not test_url:
        if TEST_DB_NAME in base_url:
            _postgres_note = f"database_url must not point at {TEST_DB_NAME}"
        else:
            _postgres_note = f"cannot parse database_url {base_url!r}"
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
    # Export the [env] table (provider keys)
    config.apply_env()
    if test_url:
        _test_url = test_url
        _postgres_note = _ensure_test_db(test_url)


def _test_postgres(url: str) -> str | None:
    """None if the test database accepts a connection, else the error message."""
    try:
        psycopg.connect(url, connect_timeout=2).close()
    except psycopg.OperationalError as exc:
        return str(exc)
    return None


# Markers that gate on a tool's presence on PATH, in tool/no_tool pairs.
# Detection runs here against the real PATH: a marked test runs only where
# the tool it exercises is genuinely available (or genuinely absent).
_PATH_GATES = {
    "sbatch": "sbatch",
    "no_sbatch": "sbatch",
    "pi": "pi",
    "no_pi": "pi",
    "faberon_chat": "faberon-chat",
    "no_faberon_chat": "faberon-chat",
}


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip tests whose infrastructure is not configured or reachable."""
    for mark, command in _PATH_GATES.items():
        if mark in item.keywords:
            found = shutil.which(command) is not None
            if mark.startswith("no_") == found:
                not_ = "no " if mark.startswith("no_") else ""
                pytest.skip(f"needs {not_}{command} on PATH")
    if "postgres" in item.keywords:
        if not _test_url or _postgres_note:
            reason = _postgres_note or f"no Postgres at {_test_url}: start it first"
            pytest.skip(reason)
        if error := _test_postgres(_test_url):
            pytest.skip(f"cannot reach the {TEST_DB_NAME} database: {error}")
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not config.slurm_account():
            pytest.skip("no slurm_account in the config file: run `faberon init`")
    if "llm" in item.keywords:
        try:
            model = config.model()
        except config.ConfigError:
            model = None
        if not model:
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
