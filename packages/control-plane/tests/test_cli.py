"""Tests for the Faberon CLI."""

import json
import uuid

import httpx2
import pytest
import uvicorn
from typer.testing import CliRunner

from faberon import cli
from faberon.api.app import GRACEFUL_SHUTDOWN_TIMEOUT
from faberon.schema import EventType

runner = CliRunner()

CAMPAIGN_ID = str(uuid.uuid4())

_PLAN = {
    "goal": "Beat val_bpb baseline.",
    "command": "echo hello",
    "target_file": "train.py",
    "metric": "val_bpb",
    "baseline": 1.42,
    "budget_gpu_hours": 100.0,
    "max_experiments": 3,
    "max_concurrency": 1,
    "walltime": 10,
    "stop_conditions": ["n/a"],
}

_CAMPAIGN_INFO = {
    "campaign": {
        "campaign_id": CAMPAIGN_ID,
        "workflow_id": CAMPAIGN_ID,
        "plan": _PLAN,
        "repo_path": "/tmp/my_repo",
        "poll_interval_seconds": 0.05,
        "created_at": "2026-10-01T03:42:22Z",
    },
    "status": "active",
    "stop_reason": None,
}

_EVENT = {
    "seq": 1,
    "ts": "2026-10-01T03:42:22Z",
    "campaign_id": CAMPAIGN_ID,
    "actor": "agent",
    "type": EventType.CAMPAIGN_CREATED.value,
    "reason": "plan accepted",
    "payload": {},
}


def _make_client(handler) -> httpx2.Client:
    return httpx2.Client(
        base_url="http://testserver",
        transport=httpx2.MockTransport(handler),
        timeout=None,
    )


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch):
    """Route the CLI's HTTP client through a mock transport."""
    responses: dict[tuple[str, str], object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=responses[(request.method, request.url.path)])

    monkeypatch.setattr(cli, "_client", lambda: _make_client(handler))
    return responses


def test_bare_command_shows_help():
    """Bare `faberon` prints help"""
    result = runner.invoke(cli.app, [])
    assert "Usage" in result.output
    assert "serve" in result.output
    assert "list" in result.output


def test_client_requires_token(monkeypatch: pytest.MonkeyPatch):
    """Without FABERON_API_TOKEN the CLI exits with guidance, not a traceback."""
    monkeypatch.delenv("FABERON_API_TOKEN", raising=False)
    result = runner.invoke(cli.app, ["list"])
    assert result.exit_code == 2
    assert "FABERON_API_TOKEN is not set" in result.output


def test_api_error_is_friendly(monkeypatch: pytest.MonkeyPatch):
    """A 404 from the API prints the server's detail, not a traceback."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "campaign not found"})

    monkeypatch.setattr(cli, "_client", lambda: _make_client(handler))
    result = runner.invoke(cli.app, ["show", CAMPAIGN_ID])
    assert result.exit_code == 1
    assert "campaign not found" in result.output
    assert "Traceback" not in result.output


def test_connection_error_is_friendly():
    """A down server prints a clear message, not a traceback."""
    # No mock: the client targets a URL with nothing listening.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("FABERON_API_TOKEN", "test-token")
    monkeypatch.setenv("FABERON_API_URL", "http://127.0.0.1:1")
    result = runner.invoke(cli.app, ["list"])
    monkeypatch.undo()
    assert result.exit_code == 1
    assert "Cannot reach" in result.output
    assert "Traceback" not in result.output


def test_serve_graceful_shutdown(monkeypatch: pytest.MonkeyPatch):
    """Production uvicorn gets a finite graceful-shutdown timeout."""
    captured = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **kw: captured.update({"args": a, "kwargs": kw})
    )

    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 0
    assert captured["kwargs"]["timeout_graceful_shutdown"] == GRACEFUL_SHUTDOWN_TIMEOUT


def _serve_factory(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the factory uvicorn is invoked with."""
    captured = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **kw: captured.update({"args": a, "kwargs": kw})
    )
    return captured


def test_serve_defaults_to_slurm(monkeypatch: pytest.MonkeyPatch):
    captured = _serve_factory(monkeypatch)
    monkeypatch.delenv("FABERON_EXECUTOR", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0] is cli.create_app_slurm
    assert "executor: slurm" in result.output


def test_serve_defaults_to_local(monkeypatch: pytest.MonkeyPatch):
    captured = _serve_factory(monkeypatch)
    monkeypatch.delenv("FABERON_EXECUTOR", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: None)
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0] is cli.create_app_local
    assert "executor: local" in result.output


def test_serve_executor_overrides(monkeypatch: pytest.MonkeyPatch):
    captured = _serve_factory(monkeypatch)
    # sbatch present, but the explicit choice wins.
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setenv("FABERON_EXECUTOR", "local")
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0] is cli.create_app_local
    assert "executor: local" in result.output


def test_serve_unknown_executor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: None)
    monkeypatch.setenv("FABERON_EXECUTOR", "kubernetes")
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 2
    assert "unknown executor" in result.output


def test_serve_host_port(monkeypatch: pytest.MonkeyPatch):
    """Flags beat env vars, which beat the defaults."""
    captured = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **kw: captured.update({"args": a, "kwargs": kw})
    )

    # Defaults
    runner.invoke(cli.app, ["serve"])
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 8000

    # Env vars override defaults
    monkeypatch.setenv("FABERON_HOST", "0.3.4.2")
    monkeypatch.setenv("FABERON_PORT", "9000")
    runner.invoke(cli.app, ["serve"])
    assert captured["kwargs"]["host"] == "0.3.4.2"
    assert captured["kwargs"]["port"] == 9000

    # Flags override env vars
    runner.invoke(cli.app, ["serve", "--host", "127.6.6.6", "--port", "9100"])
    assert captured["kwargs"]["host"] == "127.6.6.6"
    assert captured["kwargs"]["port"] == 9100


def test_list(api_client):
    api_client[("GET", "/v0/campaigns")] = [_CAMPAIGN_INFO]
    result = runner.invoke(cli.app, ["list"])
    assert result.exit_code == 0

    # Header row
    assert "ID" in result.output
    assert "CREATED" in result.output
    assert "STATUS" in result.output
    assert "METRIC" in result.output
    assert "REPO" in result.output

    # Row carries the campaign's id, status, metric, and repo path.
    assert CAMPAIGN_ID in result.output
    assert "active" in result.output
    assert "val_bpb" in result.output
    assert "/tmp/my_repo" in result.output
    assert "2026-10-01 03:42" in result.output


def test_list_json(api_client):
    api_client[("GET", "/v0/campaigns")] = [_CAMPAIGN_INFO]
    result = runner.invoke(cli.app, ["list", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["campaign"]["campaign_id"] == CAMPAIGN_ID


def test_show(api_client):
    api_client[("GET", f"/v0/campaigns/{CAMPAIGN_ID}")] = _CAMPAIGN_INFO
    result = runner.invoke(cli.app, ["show", CAMPAIGN_ID])
    assert result.exit_code == 0
    assert CAMPAIGN_ID in result.output
    assert "status:   active" in result.output
    assert "metric:   val_bpb" in result.output
    assert "budget:   100.0 gpu-hours" in result.output
    assert "max exp:  3" in result.output


def test_show_json(api_client):
    api_client[("GET", f"/v0/campaigns/{CAMPAIGN_ID}")] = _CAMPAIGN_INFO
    result = runner.invoke(cli.app, ["show", CAMPAIGN_ID, "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    campaign = parsed["campaign"]
    plan = campaign["plan"]
    assert campaign["campaign_id"] == CAMPAIGN_ID
    assert parsed["status"] == "active"
    assert plan["metric"] == "val_bpb"
    assert plan["budget_gpu_hours"] == 100.0
    assert plan["max_experiments"] == 3


def _events_handler(request: httpx2.Request) -> httpx2.Response:
    # events.jsonl returns ndjson text, one JSON event per line.
    return httpx2.Response(200, text=json.dumps(_EVENT) + "\n")


def test_events(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "_client", lambda: _make_client(_events_handler))
    result = runner.invoke(cli.app, ["events", CAMPAIGN_ID])
    assert result.exit_code == 0
    assert "campaign.created" in result.output
    assert "plan accepted" in result.output
    # Non-verbose by default: no payload block.
    assert "payload" not in result.output


def test_events_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "_client", lambda: _make_client(_events_handler))
    result = runner.invoke(cli.app, ["events", CAMPAIGN_ID, "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output.strip())
    assert parsed["type"] == EventType.CAMPAIGN_CREATED.value


def test_events_after(monkeypatch: pytest.MonkeyPatch):
    """--after is forwarded to the API as the seq lower bound."""
    captured = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["after"] = request.url.params["after"]
        return httpx2.Response(200, text=json.dumps(_EVENT) + "\n")

    monkeypatch.setattr(cli, "_client", lambda: _make_client(handler))
    result = runner.invoke(cli.app, ["events", CAMPAIGN_ID, "--after", "41"])
    assert result.exit_code == 0
    assert captured["after"] == "41"


def test_cancel(api_client):
    api_client[("POST", f"/v0/campaigns/{CAMPAIGN_ID}/cancel")] = {
        "campaign_id": CAMPAIGN_ID,
        "status": "cancel requested",
    }
    result = runner.invoke(
        cli.app, ["cancel", CAMPAIGN_ID, "--reason", "no longer needed"]
    )
    assert result.exit_code == 0
    assert "cancel requested" in result.output


def test_cancel_empty_reason(api_client):
    """An explicit empty --reason fails without prompting."""
    result = runner.invoke(cli.app, ["cancel", CAMPAIGN_ID, "--reason", "  "])
    assert result.exit_code == 2
    assert "empty" in result.output


def test_cancel_prompt(api_client, monkeypatch: pytest.MonkeyPatch):
    """With no reason flag, the prompt re-asks until the reason is non-empty."""
    api_client[("POST", f"/v0/campaigns/{CAMPAIGN_ID}/cancel")] = {
        "campaign_id": CAMPAIGN_ID,
        "status": "cancel requested",
    }
    answers = iter(["   ", "no longer needed"])
    monkeypatch.setattr(cli.typer, "prompt", lambda _p: next(answers))
    result = runner.invoke(cli.app, ["cancel", CAMPAIGN_ID])
    assert result.exit_code == 0
    assert "empty" in result.output
    assert "cancel requested" in result.output


def test_resume(api_client):
    api_client[("POST", f"/v0/campaigns/{CAMPAIGN_ID}/resume")] = {
        "campaign_id": CAMPAIGN_ID,
        "status": "resume requested",
    }
    result = runner.invoke(cli.app, ["resume", CAMPAIGN_ID])
    assert result.exit_code == 0
    assert "resume requested" in result.output


def test_create(api_client, tmp_path):
    api_client[("POST", "/v0/campaigns")] = {
        "campaign_id": CAMPAIGN_ID,
        "workflow_id": CAMPAIGN_ID,
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(_PLAN))
    result = runner.invoke(cli.app, ["create", str(plan_file), str(tmp_path)])
    assert result.exit_code == 0
    assert CAMPAIGN_ID in result.output
    assert "workflow" in result.output
