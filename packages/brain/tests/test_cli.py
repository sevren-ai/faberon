"""Tests for the Faberon CLI."""

import json
import shutil
import tomllib
import uuid

import httpx2
import pytest
import uvicorn
from typer.testing import CliRunner

from faberon import cli
from faberon.api.app import (
    GRACEFUL_SHUTDOWN_TIMEOUT,
    create_app_local,
    create_app_slurm,
)
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


def test_client_requires_token():
    """Without a token in the config file, the CLI exits with guidance."""
    result = runner.invoke(cli.app, ["list"])
    assert result.exit_code == 2
    assert "faberon init" in result.output


def test_client_reads_token_from_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """The CLI takes the token and URL from the config file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('api_token = "file-token"\napi_url = "http://127.0.0.1:1"\n')
    monkeypatch.setenv("FABERON_CONFIG", str(config_file))
    result = runner.invoke(cli.app, ["list"])
    # Past the token check: fails on the unreachable server instead.
    assert result.exit_code == 1
    assert "Cannot reach" in result.output


def test_api_error_is_friendly(monkeypatch: pytest.MonkeyPatch):
    """A 404 from the API prints the server's detail, not a traceback."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "campaign not found"})

    monkeypatch.setattr(cli, "_client", lambda: _make_client(handler))
    result = runner.invoke(cli.app, ["show", CAMPAIGN_ID])
    assert result.exit_code == 1
    assert "campaign not found" in result.output
    assert "Traceback" not in result.output


def test_connection_error_is_friendly(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A down server prints a clear message, not a traceback."""
    # No mock: the client targets a URL with nothing listening.
    config_file = tmp_path / "config.toml"
    config_file.write_text('api_token = "test-token"\napi_url = "http://127.0.0.1:1"\n')
    monkeypatch.setenv("FABERON_CONFIG", str(config_file))
    result = runner.invoke(cli.app, ["list"])
    assert result.exit_code == 1
    assert "Cannot reach" in result.output
    assert "Traceback" not in result.output


_SERVE_CONFIG = (
    'database_url = "postgres:///faberon_test"\n'
    'model = "test-model"\n'
    'host = "127.0.0.1"\n'
    "port = 8000\n"
    "proposer_timeout = 600\n"
    'state_dir = "/tmp/faberon-test-state"\n'
)

# Executor-agnostic serve behavior runs against both executors.
_SERVE_LOCAL = 'executor = "local"\n'
_SERVE_SLURM = (
    'executor = "slurm"\napi_token = "tok"\nslurm_account = "acct"\nslurm_gpus = 2\n'
)


def _serve_setup(
    tmp_path, monkeypatch: pytest.MonkeyPatch, extra_config: str = ""
) -> dict:
    """Write a servable config file and capture the uvicorn invocation."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(_SERVE_CONFIG + extra_config)
    monkeypatch.setenv("FABERON_CONFIG", str(config_file))
    # Serve preflights the DB; stub the probe, there is no live Postgres here.
    monkeypatch.setattr(cli, "_probe_db", lambda url: None)
    captured = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **kw: captured.update({"args": a, "kwargs": kw})
    )
    return captured


@pytest.mark.parametrize(
    "extra_config",
    [_SERVE_LOCAL, _SERVE_SLURM],
)
def test_serve_graceful_shutdown(
    tmp_path, monkeypatch: pytest.MonkeyPatch, extra_config: str
):
    """Production uvicorn gets a finite graceful-shutdown timeout."""
    captured = _serve_setup(tmp_path, monkeypatch, extra_config)
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["kwargs"]["timeout_graceful_shutdown"] == GRACEFUL_SHUTDOWN_TIMEOUT


def test_serve_requires_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Without the required settings, serve points at `faberon init`."""
    monkeypatch.setenv("FABERON_CONFIG", str(tmp_path / "config.toml"))
    # No file at all: everything is missing.
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 2
    assert "missing configuration: database_url, model" in result.output
    assert "faberon init" in result.output


@pytest.mark.parametrize(
    ("extra_config", "executor"),
    [(_SERVE_LOCAL, "local"), (_SERVE_SLURM, "slurm")],
)
def test_serve_prints_settings(
    tmp_path, monkeypatch: pytest.MonkeyPatch, extra_config: str, executor: str
):
    """The startup output shows what the server will run with."""
    _serve_setup(tmp_path, monkeypatch, extra_config)
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert f"executor: {executor}" in result.output
    assert "database: postgres:///faberon_test" in result.output
    assert "model:    test-model" in result.output

    # A partial file (the upgrade scenario): only the missing keys are named.
    (tmp_path / "config.toml").write_text(
        'database_url = "postgres:///faberon_test"\nmodel = "test-model"\n'
    )
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 2
    assert "missing configuration: host, port" in result.output


@pytest.mark.sbatch
def test_serve_defaults_to_slurm(tmp_path, monkeypatch: pytest.MonkeyPatch):
    captured = _serve_setup(
        tmp_path,
        monkeypatch,
        'api_token = "tok"\nslurm_account = "acct"\nslurm_gpus = 2\n',
    )
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0].func is create_app_slurm
    assert "executor: slurm" in result.output


@pytest.mark.sbatch
def test_serve_slurm_requires_token_and_account(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _serve_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 2
    assert "api_token" in result.output
    assert "slurm_account" in result.output


@pytest.mark.no_sbatch
def test_serve_defaults_to_local(tmp_path, monkeypatch: pytest.MonkeyPatch):
    captured = _serve_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0].func is create_app_local
    assert "executor: local" in result.output


def test_serve_executor_from_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """The config file's executor wins over autodetection."""
    captured = _serve_setup(tmp_path, monkeypatch, 'executor = "local"\n')
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0
    assert captured["args"][0].func is create_app_local
    assert "executor: local" in result.output


def test_serve_unknown_executor(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _serve_setup(tmp_path, monkeypatch, 'executor = "kubernetes"\n')
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 2
    assert "unknown executor" in result.output


@pytest.mark.parametrize(
    "extra_config",
    [_SERVE_LOCAL, _SERVE_SLURM],
)
def test_serve_host_port(tmp_path, monkeypatch: pytest.MonkeyPatch, extra_config: str):
    """Host and port come from the config file."""
    captured = _serve_setup(tmp_path, monkeypatch, extra_config)
    runner.invoke(cli.app, ["serve"])
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 8000

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        _SERVE_CONFIG.replace('host = "127.0.0.1"', 'host = "0.3.4.2"').replace(
            "port = 8000", "port = 9000"
        )
        + extra_config
    )
    runner.invoke(cli.app, ["serve"])
    assert captured["kwargs"]["host"] == "0.3.4.2"
    assert captured["kwargs"]["port"] == 9000


@pytest.mark.parametrize(
    "extra_config",
    [_SERVE_LOCAL, _SERVE_SLURM],
)
def test_serve_no_recover(tmp_path, monkeypatch: pytest.MonkeyPatch, extra_config: str):
    """--no-recover is forwarded to the app factory."""
    captured = _serve_setup(tmp_path, monkeypatch, extra_config)
    result = runner.invoke(cli.app, ["serve", "--no-recover"])
    assert result.exit_code == 0
    assert captured["args"][0].keywords == {"no_recover": True}


def _init_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate `init` from the developer's real setup; return the config path."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setenv("FABERON_CONFIG", str(config_file))
    monkeypatch.setattr(cli, "_POSTGRES_ENV_PATH", tmp_path / "postgres.env")
    monkeypatch.setattr(cli, "_probe_db", lambda url: None)
    return config_file


def test_init_db_default_from_postgres_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A no-sudo Postgres install's postgres.env provides the URL default."""
    config_file = _init_env(tmp_path, monkeypatch)
    (tmp_path / "postgres.env").write_text(
        "# Generated by scripts/db/install-postgres-no-sudo.sh.\n"
        'export PATH="/x/bin:\\$PATH"\n'
        'export FABERON_PG_PREFIX="/x"\n'
        'export FABERON_PG_URL="postgres://landso:secret123@localhost:54329/faberon"\n'
    )
    # Postgres URL (default from postgres.env), model, executor.
    result = runner.invoke(cli.app, ["init"], input="\ntest-model\nlocal\n")
    assert result.exit_code == 0
    data = tomllib.loads(config_file.read_text())
    assert data["database_url"] == "postgres://landso:secret123@localhost:54329/faberon"
    # The password is never shown: the prompt displays the masked URL.
    assert "secret123" not in result.output
    assert "landso:***@localhost:54329" in result.output


def test_init_notes_unknown_provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A provider without a credential prompt gets a note, not silence."""
    config_file = _init_env(tmp_path, monkeypatch)
    # Postgres URL (default), model, executor.
    result = runner.invoke(cli.app, ["init"], input="\nanthropic:claude-x\nlocal\n")
    assert result.exit_code == 0
    assert "add the credentials needed for 'anthropic'" in result.output
    data = tomllib.loads(config_file.read_text())
    assert data["model"] == "anthropic:claude-x"
    assert "env" not in data


def test_init_writes_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    config_file = _init_env(tmp_path, monkeypatch)
    # Postgres URL (default), model, OpenRouter key, executor.
    result = runner.invoke(
        cli.app, ["init"], input="\nopenrouter:x/y\nsk-test\nlocal\n"
    )
    assert result.exit_code == 0
    # The key is never echoed to the terminal.
    assert "sk-test" not in result.output
    data = tomllib.loads(config_file.read_text())
    assert data["database_url"] == "postgres:///faberon"
    assert data["model"] == "openrouter:x/y"
    assert data["executor"] == "local"
    assert data["api_token"]
    assert data["env"] == {"OPENROUTER_API_KEY": "sk-test"}
    # The file is written complete: every defaulted setting is spelled out.
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8000
    assert data["proposer_timeout"] == 600.0
    assert data["state_dir"].endswith(".local/share/faberon")
    assert "faberon serve" in result.output


@pytest.mark.sbatch
def test_init_slurm(tmp_path, monkeypatch: pytest.MonkeyPatch):
    config_file = _init_env(tmp_path, monkeypatch)
    # Postgres URL (default), model, executor (default: slurm), account, GPUs (default).
    result = runner.invoke(cli.app, ["init"], input="\ntest-model\n\nacct01\n\n")
    assert result.exit_code == 0
    data = tomllib.loads(config_file.read_text())
    assert data["executor"] == "slurm"
    assert data["slurm_account"] == "acct01"
    assert data["slurm_gpus"] == 1
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8000
    assert "env" not in data


@pytest.mark.no_sbatch
def test_init_defaults_to_local(tmp_path, monkeypatch: pytest.MonkeyPatch):
    config_file = _init_env(tmp_path, monkeypatch)
    # Postgres URL (default), model, executor (default: local).
    result = runner.invoke(cli.app, ["init"], input="\ntest-model\n\n")
    assert result.exit_code == 0
    data = tomllib.loads(config_file.read_text())
    assert data["executor"] == "local"
    assert "slurm_account" not in data


def test_init_keeps_existing_token(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Re-running init keeps the token and offers current values as defaults."""
    config_file = _init_env(tmp_path, monkeypatch)
    config_file.write_text(
        'api_token = "keep-me"\nmodel = "test-model"\nexecutor = "local"\n'
    )
    # Postgres URL, model, executor: all defaults kept.
    result = runner.invoke(cli.app, ["init"], input="\n\n\n")
    assert result.exit_code == 0
    # Keys the sparse existing file lacked are reported as filled in.
    assert "filled in new settings: host, port" in result.output
    assert "updating existing config" in result.output
    data = tomllib.loads(config_file.read_text())
    assert data["api_token"] == "keep-me"
    assert data["model"] == "test-model"


def test_init_creates_missing_database(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Server up, database missing: init creates it without asking."""
    config_file = _init_env(tmp_path, monkeypatch)
    probed: dict[str, str | None] = {"err": "database missing"}
    calls = []
    monkeypatch.setattr(cli, "_probe_db", lambda url: probed["err"])
    monkeypatch.setattr(cli, "_server_up", lambda url: None)

    def fake_create(url, pg_env):
        calls.append(url)
        probed["err"] = None

    monkeypatch.setattr(cli, "_create_db", fake_create)
    # Postgres URL (default), model, executor.
    result = runner.invoke(cli.app, ["init"], input="\ntest-model\nlocal\n")
    assert result.exit_code == 0
    assert calls == ["postgres:///faberon"]
    assert "creating database" in result.output
    assert config_file.exists()


def test_init_requires_running_postgres(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """No server: init fails with guidance instead of writing anything."""
    config_file = _init_env(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_probe_db", lambda url: "connection refused")
    monkeypatch.setattr(cli, "_server_up", lambda url: "connection refused")
    # Postgres URL (default); init exits before further prompts.
    result = runner.invoke(cli.app, ["init"], input="\n")
    assert result.exit_code == 2
    assert "cannot connect to Postgres" in result.output
    assert "connection refused" in result.output
    assert not config_file.exists()


def test_init_fails_when_createdb_fails(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Server up but the database still missing after createdb: init fails."""
    config_file = _init_env(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_probe_db", lambda url: "database missing")
    monkeypatch.setattr(cli, "_server_up", lambda url: None)
    monkeypatch.setattr(cli, "_create_db", lambda url, pg_env: None)
    result = runner.invoke(cli.app, ["init"], input="\n")
    assert result.exit_code == 2
    assert "could not create the database" in result.output
    assert not config_file.exists()


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


@pytest.mark.pi
def test_chat_uses_pi(monkeypatch: pytest.MonkeyPatch):
    """With the extension installed into Pi, `faberon chat` execs plain `pi`."""
    captured = {}

    def fake_execvp(file, args):
        captured["args"] = args
        raise cli.typer.Exit(0)  # exec replaces the process; stop here

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)
    result = runner.invoke(cli.app, ["chat", "--", "--help"])
    assert result.exit_code == 0
    # Typer strips the "--" separator; extra args arrive bare.
    assert captured["args"] == [shutil.which("pi"), "--help"]


@pytest.mark.no_pi
@pytest.mark.faberon_chat
def test_chat_falls_back_to_shim(monkeypatch: pytest.MonkeyPatch):
    """Without `pi` on PATH, `faberon chat` falls back to the npm shim."""
    captured = {}

    def fake_execvp(file, args):
        captured["args"] = args
        raise cli.typer.Exit(0)  # exec replaces the process; stop here

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)
    result = runner.invoke(cli.app, ["chat", "--version"])
    assert result.exit_code == 0
    assert captured["args"] == [shutil.which("faberon-chat"), "--version"]


@pytest.mark.no_pi
@pytest.mark.no_faberon_chat
def test_chat_without_chat_installed():
    """No `pi` and no shim: install guidance, not a traceback."""
    result = runner.invoke(cli.app, ["chat"])
    assert result.exit_code == 2
    assert "pi install npm:@faberon/chat" in result.output
    assert "packages/chat" in result.output
    assert "npm install -g @faberon/chat" in result.output
    assert "Traceback" not in result.output
