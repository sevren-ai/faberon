"""HTTP API tests. Require Postgres (``postgres`` marker)."""

import os
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import httpx2
import pytest
import uvicorn
from dbos import DBOS
from fastapi.testclient import TestClient

from faberon.api import create_app
from faberon.executor import JobInfo, JobState, SubmitRequest
from faberon.ledger import Ledger
from faberon.schema.events import EventType

pytestmark = pytest.mark.postgres


class FakeExecutor:
    """Returns a fixed terminal status on first poll"""

    def __init__(self, state: JobState, exit_code: int | None = 0) -> None:
        self._state = state
        self._exit_code = exit_code
        self.submit_count = 0

    def submit(self, request: SubmitRequest) -> str:
        self.submit_count += 1
        return "api-job-1"

    def status(self, job_id: str) -> JobInfo:
        return JobInfo(job_id=job_id, state=self._state, exit_code=self._exit_code)

    def cancel(self, job_id: str) -> None:
        pass


@dataclass
class ApiFixture:
    client: TestClient
    executor: FakeExecutor
    metric_path: str


@pytest.fixture
def api(tmp_path) -> Iterator[ApiFixture]:
    DBOS.destroy()
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    ledger._conn.execute("TRUNCATE events RESTART IDENTITY")
    ledger.close()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = FakeExecutor(JobState.COMPLETED, exit_code=0)

    config_name = f"api-test-{uuid.uuid4().hex}"
    app = create_app(executor=executor, config_name=config_name)
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


def test_create_campaign(api: ApiFixture):
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


def test_get_unknown_campaign(api: ApiFixture):
    response = api.client.get("/v0/campaigns/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404


@dataclass
class LiveServer:
    base_url: str
    executor: FakeExecutor
    metric_path: str


@pytest.fixture
def live_server(tmp_path) -> Iterator[LiveServer]:
    """Serve the app over real HTTP on 127.0.0.1."""
    DBOS.destroy()
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    ledger._conn.execute("TRUNCATE events RESTART IDENTITY")
    ledger.close()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = FakeExecutor(JobState.COMPLETED, exit_code=0)

    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start in time")
        time.sleep(0.05)

    yield LiveServer(
        base_url=f"http://127.0.0.1:{port}",
        executor=executor,
        metric_path=str(metric),
    )

    server.should_exit = True
    thread.join(timeout=10)
    DBOS.destroy()


def _read_sse_until(client: httpx2.Client, path: str, marker: str) -> list[str]:
    """Collect SSE data lines until one contains ``marker``."""
    events: list[str] = []
    with client.stream("GET", path) as stream:
        for line in stream.iter_lines():
            if line.startswith("data: "):
                events.append(line.removeprefix("data: "))
                if marker in line:
                    return events
    return events


def test_events_stream_resume(live_server: LiveServer):
    timeout = httpx2.Timeout(10.0, read=10.0)
    with httpx2.Client(base_url=live_server.base_url, timeout=timeout) as client:
        response = client.post(
            "/v0/campaigns", json=_create_body(live_server.metric_path)
        )
        assert response.status_code == 201
        campaign_id = response.json()["campaign_id"]

        handle = DBOS.retrieve_workflow(response.json()["workflow_id"])
        assert handle.get_result() == "keep"

        # Full replay from the start.
        events = _read_sse_until(client, "/v0/events", "experiment.judged")
        assert any("campaign.created" in e for e in events)
        assert any(campaign_id in e for e in events)

        # Reconnect after seq 1: skips campaign.created, streams experiment.judged
        replayed = _read_sse_until(client, "/v0/events?after=1", "experiment.judged")
        assert not any("campaign.created" in e for e in replayed)
        assert any(campaign_id in e for e in replayed)
