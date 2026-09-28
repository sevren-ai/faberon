"""FastAPI application factory and routes."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from uuid import UUID

import dbos._recovery
from dbos import DBOS, DBOSConfig, SetWorkflowID
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware import Middleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response
from starlette.types import ASGIApp

from .. import __version__
from ..executor import Executor
from ..executor.slurm import SlurmExecutor
from ..ledger import Ledger
from ..schema.campaign import Campaign, CampaignInfo, CampaignStatus
from ..schema.events import Actor, Event, EventType
from ..workflow import (
    AgentProposer,
    CampaignRunner,
    CampaignSetup,
    Runtime,
    get_campaign_info,
)
from .models import CampaignCreate, CampaignCreated, CancelCampaign

_HEALTHZ_PATH = "/healthz"
RequestResponseEndpoint = Callable[[StarletteRequest], Awaitable[Response]]

# How long uvicorn waits before cancelling open connections at shutdown, such
# as an SSE stream. This would otherwise deadlock.
GRACEFUL_SHUTDOWN_TIMEOUT = 5


def _rebuild_setup(campaign: Campaign) -> CampaignSetup:
    """Reconstruct the campaign's original inputs from its ledger row."""
    return CampaignSetup(
        campaign_id=campaign.campaign_id,
        plan=campaign.plan,
        command=campaign.command,
        repo_path=campaign.repo_path,
        poll_interval_seconds=campaign.poll_interval_seconds,
    )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests missing the expected bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(
        self, request: StarletteRequest, call_next: RequestResponseEndpoint
    ) -> Response:
        # health checks do not need the token
        if request.url.path == _HEALTHZ_PATH:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {self._token}":
            return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})


def create_app(
    executor: Executor,
    *,
    config_name: str = "default",
    auth_token: str | None = None,
) -> FastAPI:
    """Build the Faberon HTTP app.
    Requires ``FABERON_DATABASE_URL`` and ``FABERON_MODEL``.

    Configures the process-global DBOS singleton.
    """
    db_url = os.environ.get("FABERON_DATABASE_URL")
    if not db_url:
        raise RuntimeError("FABERON_DATABASE_URL is not set")

    config: DBOSConfig = {
        "name": "faberon",
        "system_database_url": db_url,
        "application_database_url": db_url,
        "run_admin_server": False,
    }
    DBOS.destroy()
    DBOS(config=config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        assert db_url is not None
        original_recovery = dbos._recovery.startup_recovery_thread
        no_recover = os.environ.get("FABERON_NO_RECOVER", "").lower() in ("1", "true", "yes")
        if no_recover:
            # Serve the API without resuming pending workflows, so the
            # operator can inspect and resume campaigns one by one.
            dbos._recovery.startup_recovery_thread = lambda *a, **k: None  # type: ignore
            logging.getLogger(__name__).info(
                "FABERON_NO_RECOVER set: not resuming pending workflows at launch"
            )
        ledger = Ledger(db_url)
        runtime = Runtime(executor, ledger, config_name=config_name)
        runner = CampaignRunner(
            runtime,
            proposer=AgentProposer.from_env(ledger),
        )
        DBOS.register_instance(runtime)
        DBOS.register_instance(runner)
        DBOS.launch()
        # The SSE stream polls the (sync) ledger off the event loop. Own pool:
        # DBOS hands its executor to asyncio.to_thread as the loop default and
        # a stream worker must not outlive DBOS.destroy() at interpreter exit.
        sse_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="faberon-sse-")
        stop_sse = asyncio.Event()
        app.state.runtime = runtime
        app.state.runner = runner
        app.state.ledger = ledger
        app.state.sse_pool = sse_pool
        app.state.stop_sse = stop_sse
        try:
            yield
        finally:
            dbos._recovery.startup_recovery_thread = original_recovery
            stop_sse.set()
            sse_pool.shutdown(wait=False, cancel_futures=True)
            DBOS.destroy()
            ledger.close()

    middleware = (
        [Middleware(BearerAuthMiddleware, token=auth_token)]
        if auth_token is not None
        else []
    )
    app = FastAPI(
        title="Faberon",
        version=__version__,
        lifespan=lifespan,
        middleware=middleware,
    )
    _register_routes(app)
    return app


def create_app_slurm() -> FastAPI:
    """Uvicorn entrypoint: Slurm executor from the environment.

    Requires ``FABERON_DATABASE_URL``, ``FABERON_SLURM_ACCOUNT``,
    ``FABERON_API_TOKEN``, and ``FABERON_MODEL``.
    Optional ``FABERON_SLURM_OUTPUT`` sets the Slurm ``--output`` path.
    Optional ``FABERON_SLURM_GPUS`` sets the GPU count per job (default 1).
    Optional ``FABERON_SLURM_MAX_TIME`` sets a walltime cap (minutes)..
    """
    account = os.environ.get("FABERON_SLURM_ACCOUNT")
    if not account:
        raise RuntimeError("FABERON_SLURM_ACCOUNT is not set")
    token = os.environ.get("FABERON_API_TOKEN")
    if not token:
        raise RuntimeError(
            "FABERON_API_TOKEN is not set. On a shared login node, "
            "localhost is reachable by other users; the API must be guarded."
        )
    gpus = int(os.environ.get("FABERON_SLURM_GPUS", "1"))
    max_walltime = os.environ.get("FABERON_SLURM_MAX_TIME")
    if max_walltime is not None:
        max_walltime = int(max_walltime)
    executor = SlurmExecutor(
        account=account,
        output=os.environ.get("FABERON_SLURM_OUTPUT"),
        gpus=gpus,
        max_walltime=max_walltime,
    )
    return create_app(executor=executor, auth_token=token)


def _register_routes(app: FastAPI) -> None:
    @app.get(_HEALTHZ_PATH)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v0/campaigns", response_model=CampaignCreated, status_code=201)
    def create_campaign(body: CampaignCreate) -> CampaignCreated:
        runner: CampaignRunner = app.state.runner
        ledger: Ledger = app.state.ledger
        campaign_id = body.campaign_id
        workflow_id = str(campaign_id)

        existing = ledger.get_campaign(campaign_id)
        if existing is None:
            # One active campaign per repo: a second one would interleave
            # commits on the same checkout.
            for other in ledger.campaigns_on_repo(body.repo_path):
                if get_campaign_info(ledger, other).status.is_active:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"repo already has an active campaign: {other.campaign_id}"
                        ),
                    )

        setup = CampaignSetup(
            campaign_id=campaign_id,
            plan=body.plan,
            command=body.command,
            repo_path=body.repo_path,
            poll_interval_seconds=body.poll_interval_seconds,
        )
        # Idempotent: DBOS dedupes on workflow id, the ledger dedupes on
        # the campaigns row. A retry with the same campaign_id returns the
        # existing campaign instead of creating a new one.
        with SetWorkflowID(workflow_id):
            handle = DBOS.start_workflow(runner.run_campaign, setup)
        ledger.create_campaign(
            campaign_id,
            workflow_id,
            body.plan,
            body.command,
            body.repo_path,
            body.poll_interval_seconds,
        )
        return CampaignCreated(
            campaign_id=campaign_id,
            workflow_id=handle.workflow_id,
        )

    @app.get("/v0/campaigns")
    def list_campaigns() -> list[CampaignInfo]:
        ledger: Ledger = app.state.ledger
        return [get_campaign_info(ledger, c) for c in ledger.list_campaigns()]

    @app.post("/v0/campaigns/{campaign_id}/cancel", status_code=202)
    def cancel_campaign(campaign_id: UUID, body: CancelCampaign) -> dict[str, str]:
        ledger: Ledger = app.state.ledger
        if ledger.get_campaign(campaign_id) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        events = ledger.campaign_events(campaign_id)
        if any(e.type == EventType.CAMPAIGN_ENDED for e in events):
            raise HTTPException(status_code=409, detail="campaign already ended")
        ledger.append(
            Event(
                campaign_id=campaign_id,
                actor=Actor.HUMAN,
                type=EventType.CANCEL_REQUESTED,
                justification=body.justification,
                payload={"source": "api"},
            )
        )
        DBOS.send(str(campaign_id), "cancel", "cancel")
        return {"campaign_id": str(campaign_id), "status": "cancel requested"}

    @app.get("/v0/campaigns/{campaign_id}")
    def get_campaign(campaign_id: UUID) -> CampaignInfo:
        ledger: Ledger = app.state.ledger
        campaign = ledger.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        return get_campaign_info(ledger, campaign)

    @app.get("/v0/campaigns/{campaign_id}/events")
    async def stream_events(
        request: Request,
        campaign_id: UUID,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        ledger: Ledger = request.app.state.ledger
        if ledger.get_campaign(campaign_id) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        sse_pool: ThreadPoolExecutor = request.app.state.sse_pool
        stop_sse: asyncio.Event = request.app.state.stop_sse
        loop = asyncio.get_running_loop()

        async def generate() -> AsyncIterator[str]:
            cursor = after
            while True:
                if stop_sse.is_set() or await request.is_disconnected():
                    break
                # Sync psycopg call; keep it off the event loop/DBOS executor
                batch = await loop.run_in_executor(
                    sse_pool,
                    lambda: list(ledger.tail(campaign_id, after=cursor)),
                )
                if stop_sse.is_set():
                    break
                for event in batch:
                    assert event.seq is not None
                    cursor = event.seq
                    yield f"event: ledger\ndata: {event.model_dump_json()}\n\n"
                # Wake early on shutdown instead of sleeping through it.
                try:
                    await asyncio.wait_for(stop_sse.wait(), timeout=0.5)
                except TimeoutError:
                    pass

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/v0/campaigns/{campaign_id}/events.jsonl")
    def read_events_jsonl(
        campaign_id: UUID,
        after: int = Query(default=0, ge=0),
    ) -> PlainTextResponse:
        """Bounded snapshot of one campaign's events, one JSON event per line."""
        ledger: Ledger = app.state.ledger
        if ledger.get_campaign(campaign_id) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        lines = [
            event.model_dump_json() for event in ledger.tail(campaign_id, after=after)
        ]
        return PlainTextResponse(
            "".join(f"{line}\n" for line in lines),
            media_type="application/x-ndjson",
        )
