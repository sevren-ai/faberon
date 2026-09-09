"""HTTP API tests. Require Postgres (``postgres`` marker)."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from dbos import DBOS
from fastapi.testclient import TestClient

from faberon.api import create_app
from faberon.executor import JobInfo, JobState, SubmitRequest
from faberon.ledger import Ledger
from faberon.schema.events import EventType

pytestmark = pytest.mark.postgres


class ScriptedExecutor:
    """Returns a fixed terminal status on first poll. Test-only."""

    def __init__(self, state: JobState, exit_code: int | None = 0) -> None:
        self._state = state
        self._exit_code = exit_code
        self.submit_count = 0

    def submit(self, request: SubmitRequest) -> str:
        self.submit_count += 1
        return "api-job-1"

    def status(self, job_id: str) -> JobInfo:
        return JobInfo(job_id=job_id, state=self._state, exit_code=self._exit_code)

    def cancel(self, job_id: str) -> None:  # pragma: no cover
        pass


@dataclass
class ApiFixture:
    client: TestClient
    executor: ScriptedExecutor
    metric_path: str


@pytest.fixture
def api(tmp_path) -> Iterator[ApiFixture]:
    DBOS.destroy()
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    ledger._conn.execute("TRUNCATE events RESTART IDENTITY")
    ledger.close()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = ScriptedExecutor(JobState.COMPLETED, exit_code=0)

    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )
    with TestClient(app) as client:
        yield ApiFixture(
            client=client,
            executor=executor,
            metric_path=str(metric),
        )
    DBOS.destroy()


def _create_body(metric_path: str) -> dict:
    return {
        "plan": {
            "goal": "Beat baseline val_bpb.",
            "metric_name": "val_bpb",
            "metric_command": f"cat {metric_path}",
            "baseline": 1.23,
            "budget_gpu_hours": 1.0,
            "max_concurrency": 1,
            "stop_conditions": ["budget exhausted"],
        },
        "command": ["true"],
        "poll_interval_seconds": 0.05,
    }


def test_create_campaign_starts_workflow(api: ApiFixture):
    response = api.client.post("/v0/campaigns", json=_create_body(api.metric_path))
    assert response.status_code == 201
    body = response.json()
    assert "campaign_id" in body
    assert "workflow_id" in body

    handle = DBOS.retrieve_workflow(body["workflow_id"])
    judgment = handle.get_result()
    assert judgment == "keep"
    assert api.executor.submit_count == 1

    status = api.client.get(f"/v0/campaigns/{body['campaign_id']}")
    assert status.status_code == 200
    types = [e["type"] for e in status.json()["events"]]
    assert types[0] == EventType.CAMPAIGN_CREATED
    assert EventType.EXPERIMENT_COMPLETED in types
    assert EventType.EXPERIMENT_JUDGED in types


def test_get_campaign_unknown_returns_404(api: ApiFixture):
    response = api.client.get("/v0/campaigns/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404
