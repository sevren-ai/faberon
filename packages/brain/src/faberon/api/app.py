"""FastAPI application factory and routes."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
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

from .. import __version__, config
from ..executor import Executor
from ..executor.local import LocalExecutor
from ..executor.slurm import SlurmExecutor
from ..ledger import Ledger
from ..schema.campaign import Campaign, CampaignInfo, Predecessor
from ..schema.events import Actor, Event, EventType
from ..schema.plan import ResearchPlan, resolve_target_in_repo
from ..workflow import (
    AgentProposer,
    CampaignRunner,
    CampaignSetup,
    Runtime,
    end_outdated_campaigns,
    get_best_kept_sha,
    get_campaign_info,
)
from ..workflow.tree import (
    branch_exists,
    checkout,
    create_branch,
    ensure_exclude,
    get_branch_tip,
    get_current_branch,
    get_current_head,
    get_uncommitted_changes,
    get_untracked_files,
    has_commits,
)
from .models import (
    CampaignCreate,
    CampaignCreated,
    CancelCampaign,
    InjectIdea,
    SuccessorCreate,
)

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
        repo_path=campaign.repo_path,
        branch=campaign.branch,
        poll_interval_seconds=campaign.poll_interval_seconds,
    )


def _get_active_campaign(ledger: Ledger, campaign_id: UUID) -> Campaign:
    """Return the campaign row, raising 404 if unknown or 409 if not active."""
    campaign = ledger.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    info = get_campaign_info(ledger, campaign)
    if not info.status.is_active:
        explanation = f"campaign not active ({info.status.value})"
        raise HTTPException(status_code=409, detail=explanation)
    return campaign


def _get_predecessor(
    ledger: Ledger, campaign_id: UUID, *, raise_when_active: bool = False
) -> tuple[Campaign, CampaignInfo]:
    """Return the predecessor row and its live info.

    Raises 404 if the campaign is unknown. With ``raise_when_active``,
    raises 409 if the campaign is still active.
    """
    predecessor = ledger.get_campaign(campaign_id)
    if predecessor is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    info = get_campaign_info(ledger, predecessor)
    if raise_when_active and info.status.is_active:
        raise HTTPException(
            status_code=409,
            detail="campaign is still active; let it end or cancel it first",
        )
    return predecessor, info


def _derive_successor_plan(
    info: CampaignInfo, *, budget_gpu_hours: float, max_experiments: int
) -> ResearchPlan:
    """The successor's plan: the predecessor's plan with fresh budget and
    limits, its baseline reseeded from the best kept metric."""
    plan = info.campaign.plan
    best_metric = info.progress.best_metric
    return plan.model_copy(
        update={
            "budget_gpu_hours": budget_gpu_hours,
            "max_experiments": max_experiments,
            "baseline": best_metric if best_metric is not None else plan.baseline,
        }
    )


def _launch_campaign(
    runner: CampaignRunner,
    ledger: Ledger,
    *,
    campaign_id: UUID,
    plan: ResearchPlan,
    repo_path: str,
    branch: str | None,
    max_gpus: int | None,
    poll_interval_seconds: float,
    succession_sha: str | None,
    lineage: Predecessor | None,
) -> CampaignCreated:
    """Validate the target repo and start the campaign workflow."""
    workflow_id = str(campaign_id)

    existing = ledger.get_campaign(campaign_id)
    if existing is None:
        # One active campaign per repo: a second one would interleave
        # commits on the same checkout.
        for other in ledger.get_campaigns_on_repo(repo_path):
            if get_campaign_info(ledger, other).status.is_active:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"repo already has an active campaign: {other.campaign_id}"
                    ),
                )

    # Reject a target file that escapes the repo before starting anything.
    try:
        resolve_target_in_repo(repo_path, plan.target_file)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # A plan may not request more GPUs per job than the deployment allows.
    if max_gpus is not None and plan.gpus > max_gpus:
        raise HTTPException(
            status_code=422,
            detail=(
                f"plan requests {plan.gpus} GPUs per job, "
                f"but this deployment caps jobs at {max_gpus} (slurm_gpus)"
            ),
        )

    # Record the repo state the campaign starts from.
    repo = Path(repo_path)
    try:
        empty = not has_commits(repo)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # A repo without commits has no HEAD to anchor the campaign on.
    if empty:
        raise HTTPException(
            status_code=409,
            detail="repo has no commits, make an initial commit first",
        )
    if succession_sha is not None:
        start_sha = succession_sha
    else:
        start_sha = get_current_head(repo)

    # A repo with uncommited changes is not allowed
    dirty = get_uncommitted_changes(repo)
    if dirty:
        error = "repo has uncommitted changes, commit or stash them first"
        raise HTTPException(status_code=409, detail=error)

    # Faberon's own run logs land in {repo}/.faberon; declare the
    # directory disposable up front.
    ensure_exclude(repo, ".faberon/")

    # Neither are untracked files outside .gitignore
    untracked = get_untracked_files(repo)
    if untracked:
        error = (
            "repo has untracked files, commit them, "
            "add them to .gitignore, or remove them first"
        )
        raise HTTPException(status_code=409, detail=error)

    if branch is None:
        if succession_sha is not None:
            # A successor commits on its own fresh branch
            branch = f"faberon/{campaign_id}"
        else:
            # Default: repo's current branch
            branch = get_current_branch(repo)
            if branch is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "repo is on a detached HEAD; check out a branch first "
                        "or name one in the `branch` field"
                    ),
                )
    if branch_exists(repo, branch):
        tip = get_branch_tip(repo, branch)
        if succession_sha is None:
            # Adopt existing branch
            start_sha = tip
        elif tip != succession_sha:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"branch {branch} already exists at {tip[:12]}; a "
                    "successor starts at the predecessor's best kept "
                    f"commit {succession_sha[:12]}, so adopting it would "
                    "strand commits. Delete the branch or pick another name"
                ),
            )
    else:
        # Create named branch
        try:
            create_branch(repo, branch, start_sha)
        except RuntimeError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    # Fail early: a checkout failure rejects the request
    try:
        checkout(repo, branch)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    setup = CampaignSetup(
        campaign_id=campaign_id,
        plan=plan,
        repo_path=repo_path,
        branch=branch,
        poll_interval_seconds=poll_interval_seconds,
    )
    # Idempotent: DBOS dedupes on workflow id, the ledger dedupes on
    # the campaigns row. A retry with the same campaign_id returns the
    # existing campaign instead of creating a new one.
    with SetWorkflowID(workflow_id):
        handle = DBOS.start_workflow(runner.run_campaign, setup)
    ledger.create_campaign(
        campaign_id,
        workflow_id,
        plan,
        repo_path,
        poll_interval_seconds,
        branch=branch,
        start_sha=start_sha,
        predecessor=lineage,
    )
    return CampaignCreated(
        campaign_id=campaign_id,
        workflow_id=handle.workflow_id,
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
    no_recover: bool = False,
    max_gpus: int | None = None,
) -> FastAPI:
    """Build the Faberon HTTP app. Configures the process-global DBOS singleton."""
    config.apply_env()
    db_url = config.database_url()

    dbos_config: DBOSConfig = {
        "name": "faberon",
        "system_database_url": db_url,
        "application_database_url": db_url,
        "run_admin_server": False,
    }
    DBOS.destroy()
    DBOS(config=dbos_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        assert db_url is not None
        original_recovery = dbos._recovery.startup_recovery_thread
        if no_recover:
            # Serve the API without resuming pending workflows, so the
            # operator can inspect and resume campaigns one by one.
            dbos._recovery.startup_recovery_thread = lambda *a, **k: None  # type: ignore
            logging.getLogger(__name__).info(
                "--no-recover set: not resuming pending workflows at launch"
            )
        ledger = Ledger(db_url)
        runtime = Runtime(executor, ledger, config_name=config_name)
        proposer = AgentProposer.from_config(ledger)
        runner = CampaignRunner(runtime, proposer=proposer)
        DBOS.register_instance(runtime)
        DBOS.register_instance(runner)
        DBOS.launch()
        # Campaigns from before an update can't be recovered, so they should be
        # ended gracefully.
        outdated = await asyncio.to_thread(end_outdated_campaigns, ledger)
        if outdated:
            logging.getLogger(__name__).warning(
                "Ended %d campaign(s) with an unrecoverable workflow: %s",
                len(outdated),
                ", ".join(str(campaign_id) for campaign_id in outdated),
            )
        # The SSE stream polls the (sync) ledger off the event loop. Own pool:
        # DBOS hands its executor to asyncio.to_thread as the loop default and
        # a stream worker must not outlive DBOS.destroy() at interpreter exit.
        sse_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="faberon-sse-")
        stop_sse = asyncio.Event()
        app.state.runtime = runtime
        app.state.runner = runner
        app.state.ledger = ledger
        app.state.max_gpus = max_gpus
        app.state.sse_pool = sse_pool
        app.state.stop_sse = stop_sse
        try:
            yield
        finally:
            dbos._recovery.startup_recovery_thread = original_recovery
            stop_sse.set()
            sse_pool.shutdown(wait=False, cancel_futures=True)
            DBOS.destroy()
            proposer.close()
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


def create_app_slurm(*, no_recover: bool = False) -> FastAPI:
    """Uvicorn entrypoint: Slurm executor from the config file."""
    account = config.slurm_account(raise_on_none=True)
    token = config.api_token(raise_on_none=True)
    gpus = config.slurm_gpus(raise_on_none=True)
    executor = SlurmExecutor(
        account=account,
        max_gpus=gpus,
        max_walltime=config.max_time(),
    )
    return create_app(
        executor=executor, auth_token=token, no_recover=no_recover, max_gpus=gpus
    )


def create_app_local(*, no_recover: bool = False) -> FastAPI:
    """Uvicorn entrypoint: local executor from the config file."""
    executor = LocalExecutor(config.state_dir(), max_walltime=config.max_time())
    return create_app(
        executor=executor, auth_token=config.api_token(), no_recover=no_recover
    )


def _register_routes(app: FastAPI) -> None:
    @app.get(_HEALTHZ_PATH)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v0/campaigns", response_model=CampaignCreated, status_code=201)
    def create_campaign(body: CampaignCreate) -> CampaignCreated:
        return _launch_campaign(
            app.state.runner,
            app.state.ledger,
            campaign_id=body.campaign_id,
            plan=body.plan,
            repo_path=body.repo_path,
            branch=body.branch,
            max_gpus=app.state.max_gpus,
            poll_interval_seconds=body.poll_interval_seconds,
            succession_sha=None,
            lineage=None,
        )

    @app.post(
        "/v0/campaigns/{campaign_id}/successor",
        response_model=CampaignCreated,
        status_code=201,
    )
    def create_successor(campaign_id: UUID, body: SuccessorCreate) -> CampaignCreated:
        """Create the successor campaign from this one's best kept commit."""
        ledger: Ledger = app.state.ledger
        predecessor, info = _get_predecessor(
            ledger, campaign_id, raise_when_active=True
        )
        plan = _derive_successor_plan(
            info,
            budget_gpu_hours=body.budget_gpu_hours,
            max_experiments=body.max_experiments,
        )
        succession_sha = get_best_kept_sha(ledger, predecessor)
        lineage = Predecessor(campaign_id=campaign_id, sha=succession_sha)
        return _launch_campaign(
            app.state.runner,
            ledger,
            campaign_id=body.campaign_id,
            plan=plan,
            repo_path=predecessor.repo_path,
            branch=body.branch,
            max_gpus=app.state.max_gpus,
            poll_interval_seconds=predecessor.poll_interval_seconds,
            succession_sha=succession_sha,
            lineage=lineage,
        )

    @app.get("/v0/campaigns")
    def list_campaigns() -> list[CampaignInfo]:
        ledger: Ledger = app.state.ledger
        return [get_campaign_info(ledger, c) for c in ledger.list_campaigns()]

    @app.post("/v0/campaigns/{campaign_id}/cancel", status_code=202)
    def cancel_campaign(campaign_id: UUID, body: CancelCampaign) -> dict[str, str]:
        ledger: Ledger = app.state.ledger
        # ensure that the campaign is known and active
        _get_active_campaign(ledger, campaign_id)
        ledger.append(
            Event(
                campaign_id=campaign_id,
                actor=Actor.HUMAN,
                type=EventType.CANCEL_REQUESTED,
                reason=body.reason,
                payload={"source": "api"},
            )
        )
        DBOS.send(str(campaign_id), "cancel", "cancel")
        return {"campaign_id": str(campaign_id), "status": "cancel requested"}

    @app.post("/v0/campaigns/{campaign_id}/ideas", status_code=202)
    def inject_idea(campaign_id: UUID, body: InjectIdea) -> dict[str, str]:
        ledger: Ledger = app.state.ledger
        # ensure that the campaign is known and active
        _get_active_campaign(ledger, campaign_id)
        ledger.append(
            Event(
                campaign_id=campaign_id,
                actor=Actor.HUMAN,
                type=EventType.IDEA_INJECTED,
                reason=body.reason,
                payload={"source": "api", "text": body.text},
            )
        )
        DBOS.send(str(campaign_id), body.text, "idea")
        return {"campaign_id": str(campaign_id), "status": "idea injected"}

    @app.post("/v0/campaigns/{campaign_id}/resume", status_code=202)
    def resume_campaign(campaign_id: UUID) -> dict[str, str]:
        """Resume a PENDING campaign's workflow from its last checkpoint."""
        runner: CampaignRunner = app.state.runner
        ledger: Ledger = app.state.ledger
        # ensure that the campaign is known and active
        campaign = _get_active_campaign(ledger, campaign_id)
        setup = _rebuild_setup(campaign)
        with SetWorkflowID(campaign.workflow_id):
            DBOS.start_workflow(runner.run_campaign, setup)
        return {"campaign_id": str(campaign_id), "status": "resume requested"}

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
