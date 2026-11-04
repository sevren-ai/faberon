"""Faberon CLI: steer campaigns from a shell."""

import contextlib
import functools
import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import psycopg
import typer
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from typer import Argument, FileText, Option, echo

from . import config
from .schema import Event, ResearchPlan

_POSTGRES_ENV_PATH = Path("~/.config/faberon/postgres.env").expanduser()

# Settings init always writes
_INIT_DEFAULTS = {
    "host": config.DEFAULT_HOST,
    "port": config.DEFAULT_PORT,
    "proposer_timeout": config.DEFAULT_PROPOSER_TIMEOUT,
    "state_dir": config.DEFAULT_STATE_DIR,
}


def _chat_install_guidance() -> None:
    """Explain how to install the chat interface, then exit."""
    echo("the chat interface is not available from this install", err=True)
    echo("install it into Pi with one of:", err=True)
    echo("  pi install npm:@faberon/chat            (published)", err=True)
    echo("  pi install /path/to/faberon/packages/chat  (from source)", err=True)
    echo("or install the standalone shim: npm install -g @faberon/chat", err=True)
    raise typer.Exit(code=2)


app = typer.Typer(
    help="Faberon: run autonomous ML research campaigns.",
    no_args_is_help=True,
)


@contextlib.contextmanager
def _client() -> Iterator[httpx2.Client]:
    """Build an API client from the config file, or exit with guidance"""
    try:
        base_url = config.api_url()
        token = config.api_token()
    except config.ConfigError as exc:
        echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    if not token:
        echo(f"no API token in {config.config_path()}: run `faberon init`", err=True)
        raise typer.Exit(code=2)
    client = httpx2.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=None,
    )
    try:
        yield client
    except httpx2.ConnectError:
        echo(f"Cannot reach the Faberon server at {base_url}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        client.close()


def _check(response: httpx2.Response) -> httpx2.Response:
    """Return the response on success or explain/exit on error status"""
    if response.is_success:
        return response
    try:
        detail = response.json().get("detail")
    except json.JSONDecodeError:
        detail = None
    echo(f"error {response.status_code}:", err=True)
    if isinstance(detail, list):
        # FastAPI validation errors: one line per offending field.
        for err in detail:
            field = ".".join(str(loc) for loc in err.get("loc", []))
            echo(f"  {field}: {err.get('msg', 'invalid')}", err=True)
    else:
        echo(f"  {detail or response.text or 'request failed'}", err=True)
    raise typer.Exit(code=1)


@app.command("serve")
def serve(
    no_recover: bool = Option(
        False, "--no-recover", help="Do not resume pending workflows at startup."
    ),
) -> None:
    """Start the Faberon server, using the config file written by `faberon init`.

    The executor defaults to `slurm` when 'sbatch' is on PATH, else `local`.
    """
    # Lazy loads to avoid startup costs for other commands.
    import uvicorn

    from .api.app import (
        GRACEFUL_SHUTDOWN_TIMEOUT,
        create_app_local,
        create_app_slurm,
    )

    factories = {"slurm": create_app_slurm, "local": create_app_local}
    settings = config.load()
    name = settings.get("executor")
    if name is not None and name not in factories.keys():
        echo(
            f"unknown executor {name!r}: expected one of {sorted(factories)}",
            err=True,
        )
        raise typer.Exit(code=2)
    if name is None:
        name = "slurm" if shutil.which("sbatch") else "local"
    required = ["database_url", "model", *_INIT_DEFAULTS]
    if name == "slurm":
        required += ["api_token", "slurm_account", "slurm_gpus"]
    missing = [key for key in required if not settings.get(key)]
    if missing:
        echo(f"missing configuration: {', '.join(missing)}", err=True)
        echo(f"run `faberon init` (config file: {config.config_path()})", err=True)
        raise typer.Exit(code=2)
    echo(f"executor: {name}")
    echo(f"database: {_redacted(settings['database_url'])}")
    echo(f"model:    {settings['model']}")
    uvicorn.run(
        functools.partial(factories[name], no_recover=no_recover),
        host=settings["host"],
        port=int(settings["port"]),
        factory=True,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT,
    )


def _postgres_env() -> dict[str, str]:
    """The no-sudo Postgres settings (postgres.env), if any.

    The file has a fixed format written by install-postgres-no-sudo.sh:
    one ``export KEY="value"`` per line.
    """
    values: dict[str, str] = {}
    if not _POSTGRES_ENV_PATH.exists():
        return values
    for line in _POSTGRES_ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        line = line.removeprefix("export ")
        key, sep, value = line.partition("=")
        if sep:
            values[key] = value.strip().strip('"')
    return values


def _redacted(url: str) -> str:
    """The URL with any password masked, for display."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return url


def _probe_db(db_url: str) -> str | None:
    """None when the database at the URL accepts a connection, else the error."""
    try:
        conn = psycopg.connect(db_url, connect_timeout=2)
        conn.close()
        return None
    except psycopg.OperationalError as exc:
        return " ".join(str(exc).split())


def _server_up(db_url: str) -> str | None:
    """None when the Postgres server is running, else the connection error."""
    maintenance = (
        make_url(db_url).set(database="postgres").render_as_string(hide_password=False)
    )
    return _probe_db(maintenance)


def _create_db(db_url: str, pg_env: dict[str, str]) -> None:
    """Create the database"""
    search_path = os.environ.get("PATH", "")
    prefix = pg_env.get("FABERON_PG_PREFIX")
    if prefix:
        search_path = f"{prefix}/bin:{search_path}"
    createdb = shutil.which("createdb", path=search_path)
    if createdb is None:
        echo(
            "createdb not found: install Postgres and put its tools on PATH, "
            "then re-run `faberon init`",
            err=True,
        )
        return
    try:
        url = make_url(db_url)
    except ArgumentError:
        echo(f"cannot parse a database name from {db_url!r}", err=True)
        return
    args = [createdb]
    if url.host:
        args += ["-h", url.host]
    if url.port:
        args += ["-p", str(url.port)]
    args.append(url.database or "faberon")
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        echo(f"Creating the DB failed: {result.stderr.strip()}", err=True)
        echo("is Postgres running? Ensure it is, then re-run `faberon init`", err=True)


@app.command("init")
def init() -> None:
    """Set up Faberon: write the config file and create the database.

    Requires a running Postgres.
    Generates the API token and records the model and executor settings.
    """
    path = config.config_path()
    try:
        existing = config.load()
    except config.ConfigError as exc:
        echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    if existing:
        echo(f"updating existing config at {path}")
    echo("press Enter to accept the proposed default shown in brackets []")
    pg_env = _postgres_env()

    db_default = (
        existing.get("database_url")
        or pg_env.get("FABERON_PG_URL")
        or config.DEFAULT_DB_URL
    )
    db_url = (
        typer.prompt(
            f"Postgres URL [{_redacted(db_default)}]", default="", show_default=False
        )
        or db_default
    )
    if _probe_db(db_url) is not None:
        if (up_err := _server_up(db_url)) is not None:
            echo(
                f"cannot connect to Postgres at {_redacted(db_url)}: {up_err}",
                err=True,
            )
            echo(
                "start Postgres first (install guide, step A1 or B1); if it is "
                "already running, check the URL's credentials "
                "(docs/troubleshooting.md)",
                err=True,
            )
            raise typer.Exit(code=2)
        echo(f"creating database for {_redacted(db_url)}")
        _create_db(db_url, pg_env)
        if (err := _probe_db(db_url)) is not None:
            echo(
                f"could not create the database ({err}); create it with createdb, "
                "then re-run `faberon init`",
                err=True,
            )
            raise typer.Exit(code=2)

    token = existing.get("api_token") or config.generate_token()
    model = typer.prompt(
        "LLM model (for example openrouter:provider/model)",
        default=existing.get("model"),
    )
    env_values: dict[str, str] = dict(existing.get("env", {}))
    if model.startswith("openrouter:"):
        key = typer.prompt(
            "OpenRouter API key",
            default=env_values.get("OPENROUTER_API_KEY") or "",
        )
        if key:
            env_values["OPENROUTER_API_KEY"] = key
    elif model.startswith("openai:"):
        base = typer.prompt(
            "OpenAI-compatible base URL",
            default=env_values.get("OPENAI_BASE_URL") or "",
        )
        if base:
            env_values["OPENAI_BASE_URL"] = base
        key = typer.prompt(
            "OpenAI-compatible API key",
            default=env_values.get("OPENAI_API_KEY") or "",
        )
        if key:
            env_values["OPENAI_API_KEY"] = key
    else:
        provider = "model"
        if ":" in model:
            provider = model.split(":")[0]
        echo(
            f"note: add the credentials needed for {provider!r} "
            "to the [env] section in the config file"
        )

    detected = "slurm" if shutil.which("sbatch") else "local"
    executor = typer.prompt(
        "Executor (slurm or local)",
        default=existing.get("executor") or detected,
    )
    if executor not in ("slurm", "local"):
        echo(f"unknown executor {executor!r}: expected slurm or local", err=True)
        raise typer.Exit(code=2)

    # Write all configuration settings
    values = {key: value for key, value in existing.items() if key != "env"}
    values.update(
        {
            "api_token": token,
            "database_url": db_url,
            "model": model,
            "executor": executor,
        }
    )
    added = [key for key in _INIT_DEFAULTS if key not in existing]
    for key, default in _INIT_DEFAULTS.items():
        values[key] = existing.get(key) or default
    if existing and added:
        echo(f"filled in new settings: {', '.join(added)}")
    if executor == "slurm":
        values["slurm_account"] = typer.prompt(
            "Slurm account",
            default=existing.get("slurm_account"),
        )
        values["slurm_gpus"] = typer.prompt(
            "GPUs per job", type=int, default=int(existing.get("slurm_gpus", 1))
        )
    else:
        values.pop("slurm_account", None)
        values.pop("slurm_gpus", None)

    config.write(path, values, env_values)
    echo(f"wrote {path} (private to your user)")
    echo("start the server with: faberon serve")


@app.command("create")
def create_campaign(
    plan: FileText = Argument(..., help="JSON file with the research plan."),
    repo: Path = Argument(
        Path("."),
        help="Path to the target repo.",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    poll: float = Option(30.0, "--poll", "-p", help="Poll interval in seconds."),
) -> None:
    """Submit a new campaign from a research plan."""
    try:
        data = json.load(plan)
    except json.JSONDecodeError as exc:
        echo(f"invalid JSON in {plan.name}: {exc}", err=True)
        echo("hint: no comments, no trailing commas, double quotes only.", err=True)
        raise typer.Exit(code=2) from None
    try:
        validated = ResearchPlan.model_validate(data)
    except ValidationError as exc:
        echo(f"invalid plan in {plan.name}:", err=True)
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            echo(f"  {field}: {err['msg']}", err=True)
        raise typer.Exit(code=2) from None
    payload = {
        "campaign_id": str(uuid4()),
        "plan": validated.model_dump(mode="json"),
        "repo_path": str(repo),
        "poll_interval_seconds": poll,
    }
    with _client() as client:
        response = _check(client.post("/v0/campaigns", json=payload))
        created = response.json()
        echo(f"campaign: {created['campaign_id']}")
        echo(f"workflow: {created['workflow_id']}")


@app.command("list")
def list_campaigns(
    as_json: bool = Option(False, "--json", "-j", help="Emit machine-readable JSON."),
) -> None:
    """List all campaigns with their live status."""
    with _client() as client:
        response = _check(client.get("/v0/campaigns"))
        infos = response.json()
        if as_json:
            echo(json.dumps(infos, indent=2))
            return
        echo(f"{'ID':<36}  {'CREATED':<16}  {'STATUS':<6}  {'METRIC':<12}  REPO")
        for info in infos:
            campaign = info["campaign"]
            created = datetime.fromisoformat(campaign["created_at"])
            line = (
                f"{campaign['campaign_id']}  "
                f"{created.strftime('%Y-%m-%d %H:%M')}  "
                f"{info['status']:<6}  "
                f"{campaign['plan']['metric']:<12}  "
                f"{campaign['repo_path']}"
            )
            echo(line)


@app.command("show")
def show_campaign(
    campaign_id: UUID,
    as_json: bool = Option(False, "--json", "-j", help="Emit machine-readable JSON."),
) -> None:
    """Show one campaign's status and plan."""
    with _client() as client:
        response = _check(client.get(f"/v0/campaigns/{campaign_id}"))
        info = response.json()
        if as_json:
            echo(json.dumps(info, indent=2))
            return
        campaign = info["campaign"]
        created = datetime.fromisoformat(campaign["created_at"])
        echo(f"campaign: {campaign['campaign_id']}")
        echo(f"created:  {created.strftime('%Y-%m-%d %H:%M')}")
        echo(f"repo:     {campaign['repo_path']}")
        echo(f"goal:     {campaign['plan']['goal']}")
        echo(f"metric:   {campaign['plan']['metric']}")
        echo(f"budget:   {campaign['plan']['budget_gpu_hours']} gpu-hours")
        echo(f"max exp:  {campaign['plan']['max_experiments']}")
        echo(f"status:   {info['status']}")
        if info["stop_reason"] is not None:
            echo(f"reason:   {info['stop_reason']}")


@app.command("events")
def campaign_events(
    campaign_id: UUID,
    follow: bool = Option(False, "--follow", "-f", help="Stream new events live."),
    after: int = Option(
        0, "--after", min=0, help="Skip events with seq up to this one."
    ),
    verbose: bool = Option(False, "--verbose", "-v", help="Show event details."),
    as_json: bool = Option(
        False, "--json", "-j", help="Emit raw events as JSONL, one per line."
    ),
) -> None:
    """Print the campaign's ledger. With ``--follow``, stream it live."""

    def _render(event: Event) -> str:
        return event.model_dump_json() if as_json else event.format(verbose=verbose)

    with _client() as client:
        if not follow:
            response = _check(
                client.get(
                    f"/v0/campaigns/{campaign_id}/events.jsonl",
                    params={"after": after},
                )
            )
            for line in response.text.splitlines():
                echo(_render(Event.model_validate_json(line)))
            return
        with client.stream(
            "GET",
            f"/v0/campaigns/{campaign_id}/events",
            params={"after": after},
        ) as stream:
            _check(stream)
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    event = Event.model_validate_json(line.removeprefix("data: "))
                    echo(_render(event))


def _read_reason() -> str:
    """Prompt until the reason is non-empty."""
    while True:
        value = typer.prompt("Reason to cancel").strip()
        if value:
            return value
        echo("Reason must not be empty", err=True)


@app.command("cancel")
def cancel_campaign(
    campaign_id: UUID,
    reason: str | None = Option(
        None, "--reason", "-r", help="Why the campaign is cancelled."
    ),
) -> None:
    """Request cancellation of an active campaign."""
    if reason is None:
        reason = _read_reason()
    elif not reason.strip():
        echo("reason must not be empty", err=True)
        raise typer.Exit(code=2)
    with _client() as client:
        response = _check(
            client.post(
                f"/v0/campaigns/{campaign_id}/cancel",
                json={"reason": reason},
            )
        )
        echo(response.json()["status"])


@app.command("resume")
def resume_campaign(campaign_id: UUID) -> None:
    """Resume a pending campaign from its last checkpoint."""
    with _client() as client:
        response = _check(client.post(f"/v0/campaigns/{campaign_id}/resume"))
        echo(response.json()["status"])


@app.command(
    "chat",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def chat(ctx: typer.Context) -> None:
    """Start the Faberon Chat interface (a Pi session with the extension loaded).

    Extra arguments are passed through to Pi.
    """
    # Hand over to the installed chat interface. `pi install` (npm or a local
    # source path) registers the extension so plain `pi` auto-loads it; the
    # `faberon-chat` npm shim is the standalone alternative. Neither is set up
    # by this command.
    pi = shutil.which("pi")
    if pi is not None:
        os.execvp(pi, [pi, *ctx.args])
    shim = shutil.which("faberon-chat")
    if shim is not None:
        os.execvp(shim, [shim, *ctx.args])
    _chat_install_guidance()


def main() -> None:
    """Console entry point."""
    app()
