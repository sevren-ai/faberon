"""Faberon CLI: steer campaigns from a shell."""

import contextlib
import json
import os
import shutil
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import typer
import uvicorn
from typer import Argument, FileText, Option, echo

from .api.app import GRACEFUL_SHUTDOWN_TIMEOUT, create_app_local, create_app_slurm
from .schema import Event

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
_DEFAULT_API_URL = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"

app = typer.Typer(
    help="Faberon: run autonomous ML research campaigns.",
    no_args_is_help=True,
)


@contextlib.contextmanager
def _client() -> Iterator[httpx2.Client]:
    """Build an API client from the environment, or exit with guidance"""
    base_url = os.environ.get("FABERON_API_URL", _DEFAULT_API_URL)
    token = os.environ.get("FABERON_API_TOKEN")
    if not token:
        echo("FABERON_API_TOKEN is not set", err=True)
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
    message = detail or response.text or "request failed"
    echo(f"error {response.status_code}: {message}", err=True)
    raise typer.Exit(code=1)


@app.command("serve")
def serve(
    host: str = Option(_DEFAULT_HOST, envvar="FABERON_HOST"),
    port: int = Option(_DEFAULT_PORT, envvar="FABERON_PORT"),
    executor: str | None = Option(None, envvar="FABERON_EXECUTOR"),
) -> None:
    """Start the Faberon server, with the given executor or a default one.

    Requires FABERON_DATABASE_URL, FABERON_API_TOKEN and FABERON_MODEL.
    The Slurm executor also requires FABERON_SLURM_ACCOUNT.
    """
    factories = {"slurm": create_app_slurm, "local": create_app_local}
    # validate given executor name
    name = executor
    if name is not None and name not in factories.keys():
        echo(
            f"unknown executor {name!r}: expected one of {sorted(factories)}",
            err=True,
        )
        raise typer.Exit(code=2)
    # default name if none was given: slurm if 'sbatch' is available
    if name is None:
        name = "slurm" if shutil.which("sbatch") else "local"
    echo(f"executor: {name}")
    uvicorn.run(
        factories.get(name),
        host=host,
        port=port,
        factory=True,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT,
    )


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
    payload = {
        "campaign_id": str(uuid4()),
        "plan": json.load(plan),
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
                f"{campaign['plan']['metric_name']:<12}  "
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
        echo(f"metric:   {campaign['plan']['metric_name']}")
        echo(f"budget:   {campaign['plan']['budget_gpu_hours']} gpu-hours")
        echo(f"max exp:  {campaign['plan']['max_experiments']}")
        echo(f"status:   {info['status']}")
        if info["stop_reason"] is not None:
            echo(f"reason:   {info['stop_reason']}")


@app.command("events")
def campaign_events(
    campaign_id: UUID,
    follow: bool = Option(False, "--follow", "-f", help="Stream new events live."),
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
            response = _check(client.get(f"/v0/campaigns/{campaign_id}/events.jsonl"))
            for line in response.text.splitlines():
                echo(_render(Event.model_validate_json(line)))
            return
        with client.stream("GET", f"/v0/campaigns/{campaign_id}/events") as stream:
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


def main() -> None:
    """Console entry point."""
    app()
