"""Shared fixtures and helpers for HTTP API tests."""

import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from dbos import DBOS
from fastapi.testclient import TestClient

from faberon import config
from faberon.api import create_app
from faberon.executor import JobState
from faberon.ledger import Ledger
from faberon.workflow import AgentProposer

from .._fakes import FakeExecutor, FakeProposer
from ..conftest import make_plan


@pytest.fixture(autouse=True)
def _fake_proposer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the LLM proposer with a deterministic one for API tests."""
    monkeypatch.setattr(
        AgentProposer, "from_config", classmethod(lambda cls, events: FakeProposer())
    )


@dataclass
class ApiFixture:
    client: TestClient
    executor: FakeExecutor
    repo_path: str


def _reset_databases() -> None:
    """Clear workflow and ledger state between API tests."""
    DBOS.reset_system_database(truncate=True)
    ledger = Ledger(config.database_url())
    ledger._conn.execute("TRUNCATE events RESTART IDENTITY")
    ledger._conn.execute("TRUNCATE campaigns")
    ledger.close()


@pytest.fixture
def api(tmp_path, repo) -> Iterator[ApiFixture]:
    DBOS.destroy()

    executor = FakeExecutor(JobState.COMPLETED, exit_code=0)

    config_name = f"api-test-{uuid.uuid4().hex}"
    app = create_app(
        executor=executor,
        config_name=config_name,
    )
    _reset_databases()
    with TestClient(app) as client:
        yield ApiFixture(
            client=client,
            executor=executor,
            repo_path=str(repo),
        )
    DBOS.destroy()


def _create_body(campaign_id: str, repo_path: str) -> dict:
    plan = make_plan(budget_gpu_hours=1.0, max_experiments=3)
    return {
        "campaign_id": campaign_id,
        "plan": plan.model_dump(mode="json"),
        "repo_path": repo_path,
        "poll_interval_seconds": 0.05,
    }


def _git(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
