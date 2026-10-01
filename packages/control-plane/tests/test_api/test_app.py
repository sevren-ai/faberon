"""HTTP API tests. Require Postgres (``postgres`` marker)."""

import json
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
from faberon.executor import JobState
from faberon.ledger import Ledger
from faberon.schema import EventType
from faberon.workflow import AgentProposer

from .._fakes import FakeExecutor, FakeProposer
from ..conftest import make_plan

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _fake_proposer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the LLM proposer with a deterministic one for API tests."""
    monkeypatch.setattr(
        AgentProposer, "from_env", classmethod(lambda cls, events: FakeProposer())
    )


@dataclass
class ApiFixture:
    client: TestClient
    executor: FakeExecutor
    metric_path: str
    repo_path: str


def _reset_databases() -> None:
    """Clear workflow and ledger state between API tests."""
    DBOS.reset_system_database(truncate=True)
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    ledger._conn.execute("TRUNCATE events RESTART IDENTITY")
    ledger._conn.execute("TRUNCATE campaigns")
    ledger.close()


@pytest.fixture
def api(tmp_path, repo) -> Iterator[ApiFixture]:
    DBOS.destroy()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
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
            metric_path=str(metric),
            repo_path=str(repo),
        )
    DBOS.destroy()


def _create_body(metric_path: str, campaign_id: str, repo_path: str) -> dict:
    plan = make_plan(
        metric_command=f"cat {metric_path}", budget_gpu_hours=1.0, max_experiments=3
    )
    return {
        "campaign_id": campaign_id,
        "plan": plan.model_dump(mode="json"),
        "command": ["true"],
        "repo_path": repo_path,
        "poll_interval_seconds": 0.05,
    }


def test_create_campaign(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    response = api.client.post(
        "/v0/campaigns", json=_create_body(api.metric_path, camp_id, api.repo_path)
    )
    assert response.status_code == 201
    body = response.json()
    assert "campaign_id" in body
    assert "workflow_id" in body

    handle = DBOS.retrieve_workflow(body["workflow_id"])
    stop_reason = handle.get_result()
    assert stop_reason == "max_experiments"
    assert api.executor.submit_count == 3

    response = api.client.get(f"/v0/campaigns/{body['campaign_id']}/events.jsonl")
    types = [json.loads(line)["type"] for line in response.text.splitlines()]
    assert types[0] == EventType.CAMPAIGN_CREATED
    assert EventType.EXPERIMENT_COMPLETED in types
    assert EventType.EXPERIMENT_JUDGED in types


def test_get_campaign(api: ApiFixture):
    body = _create_body(api.metric_path, str(uuid.uuid4()), api.repo_path)
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    response = api.client.get(f"/v0/campaigns/{body['campaign_id']}")
    assert response.status_code == 200
    info = response.json()
    assert info["status"] == "ended"
    assert info["stop_reason"] == "max_experiments"
    campaign = info["campaign"]
    assert campaign["campaign_id"] == body["campaign_id"]
    assert campaign["plan"]["goal"] == body["plan"]["goal"]
    assert "created_at" in campaign


def test_list_campaigns(api: ApiFixture):
    assert api.client.get("/v0/campaigns").json() == []
    ids = [str(uuid.uuid4()) for _ in range(2)]
    for cid in ids:
        response = api.client.post(
            "/v0/campaigns", json=_create_body(api.metric_path, cid, api.repo_path)
        )
        assert response.status_code == 201
        DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    response = api.client.get("/v0/campaigns")
    assert response.status_code == 200
    campaigns = response.json()
    assert [c["campaign"]["campaign_id"] for c in campaigns] == ids
    assert {c["status"] for c in campaigns} == {"ended"}


def test_get_unknown_campaign(api: ApiFixture):
    unknown = "00000000-0000-0000-0000-000000000099"
    assert api.client.get(f"/v0/campaigns/{unknown}").status_code == 404
    assert api.client.get(f"/v0/campaigns/{unknown}/events").status_code == 404
    assert api.client.get(f"/v0/campaigns/{unknown}/events.jsonl").status_code == 404


def _inject_body(text: str = "try a cosine schedule") -> dict:
    return {"text": text, "reason": "operator hunch"}


def test_inject_idea(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    created = api.client.post(
        "/v0/campaigns", json=_create_body(api.metric_path, camp_id, api.repo_path)
    )
    assert created.status_code == 201

    response = api.client.post(f"/v0/campaigns/{camp_id}/ideas", json=_inject_body())
    assert response.status_code == 202
    assert response.json() == {"campaign_id": camp_id, "status": "idea injected"}

    DBOS.retrieve_workflow(created.json()["workflow_id"]).get_result()
    events = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    ideas = [
        json.loads(line)
        for line in events.text.splitlines()
        if json.loads(line)["type"] == EventType.IDEA_INJECTED
    ]
    assert len(ideas) == 1
    assert ideas[0]["actor"] == "human"
    assert ideas[0]["reason"] == "operator hunch"
    assert ideas[0]["payload"]["text"] == "try a cosine schedule"
    assert ideas[0]["payload"]["source"] == "api"


def test_inject_idea_unknown_campaign(api: ApiFixture):
    unknown = "00000000-0000-0000-0000-000000000099"
    response = api.client.post(f"/v0/campaigns/{unknown}/ideas", json=_inject_body())
    assert response.status_code == 404


def test_inject_idea_ended_campaign(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    created = api.client.post(
        "/v0/campaigns", json=_create_body(api.metric_path, camp_id, api.repo_path)
    )
    assert created.status_code == 201
    DBOS.retrieve_workflow(created.json()["workflow_id"]).get_result()

    response = api.client.post(f"/v0/campaigns/{camp_id}/ideas", json=_inject_body())
    assert response.status_code == 409
    events = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    assert EventType.IDEA_INJECTED not in {
        json.loads(line)["type"] for line in events.text.splitlines()
    }


def test_inject_idea_requires_reason(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    created = api.client.post(
        "/v0/campaigns", json=_create_body(api.metric_path, camp_id, api.repo_path)
    )
    assert created.status_code == 201

    # Missing reason
    response = api.client.post(
        f"/v0/campaigns/{camp_id}/ideas", json={"text": "try a cosine schedule"}
    )
    assert response.status_code == 422
    # Empty reason
    response = api.client.post(
        f"/v0/campaigns/{camp_id}/ideas",
        json={"text": "try a cosine schedule", "reason": ""},
    )
    assert response.status_code == 422
    DBOS.retrieve_workflow(created.json()["workflow_id"]).get_result()


def test_events_jsonl(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    for cid in (camp_id, other_id):
        response = api.client.post(
            "/v0/campaigns", json=_create_body(api.metric_path, cid, api.repo_path)
        )
        assert response.status_code == 201
        DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    response = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == EventType.CAMPAIGN_CREATED
    assert EventType.EXPERIMENT_JUDGED in {e["type"] for e in events}
    # The path scopes the read: no events from the other campaign.
    assert all(e["campaign_id"] == camp_id for e in events)

    # `after` skips earlier events.
    response = api.client.get(
        f"/v0/campaigns/{camp_id}/events.jsonl", params={"after": 1}
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert all(e["seq"] > 1 for e in events)
    assert EventType.CAMPAIGN_CREATED not in {e["type"] for e in events}


def test_healthz(api: ApiFixture):
    response = api.client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth(tmp_path, repo):
    DBOS.destroy()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = FakeExecutor(JobState.COMPLETED, exit_code=0)
    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
        auth_token="my-secret-token",
    )
    _reset_databases()
    headers = {"Authorization": "Bearer my-secret-token"}
    body = _create_body(str(metric), str(uuid.uuid4()), str(repo))
    with TestClient(app) as client:
        # healthz is always open
        assert client.get("/healthz").status_code == 200
        # without token: rejected
        assert client.post("/v0/campaigns", json=body).status_code == 401
        # with token: accepted
        response = client.post("/v0/campaigns", json=body, headers=headers)
        assert response.status_code == 201
        handle = DBOS.retrieve_workflow(response.json()["workflow_id"])
        assert handle.get_result() == "max_experiments"
    DBOS.destroy()


def test_create_campaign_idempotent(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    body = _create_body(api.metric_path, camp_id, api.repo_path)
    first = api.client.post("/v0/campaigns", json=body)
    assert first.status_code == 201
    DBOS.retrieve_workflow(first.json()["workflow_id"]).get_result()

    # Retry with the same campaign_id: no duplicate workflow, no duplicate event.
    second = api.client.post("/v0/campaigns", json=body)
    assert second.status_code == 201
    assert second.json()["campaign_id"] == first.json()["campaign_id"]
    assert second.json()["workflow_id"] == first.json()["workflow_id"]
    assert api.executor.submit_count == 3

    status = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    types = [json.loads(line)["type"] for line in status.text.splitlines()]
    assert types.count(EventType.CAMPAIGN_CREATED) == 1


def test_resume_pending_campaign(api: ApiFixture):
    """Resume replays a pending campaign from its checkpoints, exactly once."""
    executor = api.executor
    assert isinstance(executor, FakeExecutor)
    # Park the campaign mid-poll: the job stays RUNNING, the workflow PENDING.
    executor._state = JobState.RUNNING
    camp_id = str(uuid.uuid4())
    created = api.client.post(
        "/v0/campaigns", json=_create_body(api.metric_path, camp_id, api.repo_path)
    )
    assert created.status_code == 201
    workflow_id = created.json()["workflow_id"]

    # Resume from the parked state. The workflow was already started by POST
    # /v0/campaigns, so resume re-attaches without resubmitting.
    executor._state = JobState.COMPLETED
    resumed = api.client.post(f"/v0/campaigns/{camp_id}/resume")
    assert resumed.status_code == 202
    result = DBOS.retrieve_workflow(workflow_id).get_result()
    assert result == "max_experiments"
    # Exactly-once: resume did not resubmit the parked first job.
    assert executor.submit_count == 3


def test_second_campaign_rejected(tmp_path, repo):
    """While one campaign is active on a repo, a second one is rejected."""
    DBOS.destroy()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = FakeExecutor(JobState.RUNNING)
    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )
    _reset_databases()
    with TestClient(app) as client:
        first = client.post(
            "/v0/campaigns",
            json=_create_body(str(metric), str(uuid.uuid4()), str(repo)),
        )
        assert first.status_code == 201

        # The running campaign reads active.
        info = client.get(f"/v0/campaigns/{first.json()['campaign_id']}").json()
        assert info["status"] == "active"
        assert info["stop_reason"] is None

        conflict = client.post(
            "/v0/campaigns",
            json=_create_body(str(metric), str(uuid.uuid4()), str(repo)),
        )
        assert conflict.status_code == 409
        assert first.json()["campaign_id"] in conflict.json()["detail"]

        # A different repo path is unaffected.
        other = tmp_path / "other-repo"
        accepted = client.post(
            "/v0/campaigns",
            json=_create_body(str(metric), str(uuid.uuid4()), str(other)),
        )
        assert accepted.status_code == 201
    DBOS.destroy()


def test_no_conflict_with_ended_campaigns(api: ApiFixture):
    """Once the campaign on a repo ends, a new one on the same repo is accepted."""
    first = api.client.post(
        "/v0/campaigns",
        json=_create_body(api.metric_path, str(uuid.uuid4()), api.repo_path),
    )
    assert first.status_code == 201
    first_id = first.json()["campaign_id"]

    # End the first campaign; the workflow completes and frees the repo.
    DBOS.retrieve_workflow(first.json()["workflow_id"]).get_result()
    info = api.client.get(f"/v0/campaigns/{first_id}").json()
    assert info["status"] == "ended"
    events = api.client.get(f"/v0/campaigns/{first_id}/events.jsonl")
    types = [json.loads(line)["type"] for line in events.text.splitlines()]
    assert EventType.CAMPAIGN_ENDED in types

    # Submit the second: should be no issue
    second = api.client.post(
        "/v0/campaigns",
        json=_create_body(api.metric_path, str(uuid.uuid4()), api.repo_path),
    )
    assert second.status_code == 201


def test_resume_ended_campaign_rejected(api: ApiFixture):
    response = api.client.post(
        "/v0/campaigns",
        json=_create_body(api.metric_path, str(uuid.uuid4()), api.repo_path),
    )
    assert response.status_code == 201
    campaign_id = response.json()["campaign_id"]
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()
    assert api.client.get(f"/v0/campaigns/{campaign_id}").json()["status"] == "ended"

    resumed = api.client.post(f"/v0/campaigns/{campaign_id}/resume")
    assert resumed.status_code == 409


def test_resume_unknown_campaign(api: ApiFixture):
    unknown = "00000000-0000-0000-0000-000000000042"
    assert api.client.post(f"/v0/campaigns/{unknown}/resume").status_code == 404


@dataclass
class LiveServer:
    base_url: str
    executor: FakeExecutor
    metric_path: str
    repo_path: str
    server: uvicorn.Server
    thread: threading.Thread
    shutdown_timeout: int


@pytest.fixture
def live_server(tmp_path, repo) -> Iterator[LiveServer]:
    """Serve the app over real HTTP on 127.0.0.1."""
    DBOS.destroy()

    metric = tmp_path / "metric.txt"
    metric.write_text("val_bpb: 1.10\n")
    executor = FakeExecutor(JobState.COMPLETED, exit_code=0)

    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )
    _reset_databases()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    # A short graceful-shutdown window keeps the test fast
    shutdown_timeout = 2
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=shutdown_timeout,
    )
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
        repo_path=str(repo),
        server=server,
        thread=thread,
        shutdown_timeout=shutdown_timeout,
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
    camp_id = str(uuid.uuid4())
    with httpx2.Client(base_url=live_server.base_url, timeout=timeout) as client:
        response = client.post(
            "/v0/campaigns",
            json=_create_body(live_server.metric_path, camp_id, live_server.repo_path),
        )
        assert response.status_code == 201
        campaign_id = response.json()["campaign_id"]

        handle = DBOS.retrieve_workflow(response.json()["workflow_id"])
        assert handle.get_result() == "max_experiments"

        # Full replay from the start.
        events = _read_sse_until(
            client, f"/v0/campaigns/{campaign_id}/events", "experiment.judged"
        )
        assert any("campaign.created" in e for e in events)
        assert any(campaign_id in e for e in events)

        # Reconnect after seq 1: skips campaign.created, streams experiment.judged
        replayed = _read_sse_until(
            client, f"/v0/campaigns/{campaign_id}/events?after=1", "experiment.judged"
        )
        assert not any("campaign.created" in e for e in replayed)
        assert any(campaign_id in e for e in replayed)


def test_shutdown_with_sse_stream(live_server: LiveServer):
    """The server stops on should_exit even with an SSE stream held open"""
    camp_id = str(uuid.uuid4())
    with httpx2.Client(base_url=live_server.base_url, timeout=10.0) as client:
        response = client.post(
            "/v0/campaigns",
            json=_create_body(live_server.metric_path, camp_id, live_server.repo_path),
        )
        assert response.status_code == 201
        campaign_id = response.json()["campaign_id"]
        DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

        # Open a stream and keep it open across the shutdown. The server stops
        # after the graceful-shutdown window plus a small teardown margin.
        with client.stream("GET", f"/v0/campaigns/{campaign_id}/events"):
            live_server.server.should_exit = True
            live_server.thread.join(timeout=live_server.shutdown_timeout + 5)
            assert not live_server.thread.is_alive(), (
                "server did not stop with an SSE stream attached"
            )
