"""FastAPI application factory and routes."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from dbos import DBOS, DBOSConfig
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import __version__
from ..executor import Executor
from ..executor.slurm import SlurmExecutor
from ..ledger import Ledger
from ..schema.events import Actor, Event, EventType
from ..workflow import ExperimentSetup, Runtime
from .models import CampaignCreate, CampaignCreated, CampaignStatus


def create_app(executor: Executor, *, config_name: str = "default") -> FastAPI:
    """Build the Faberon HTTP app. Requires ``FABERON_DATABASE_URL``."""
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
        ledger = Ledger(db_url)
        runtime = Runtime(executor, ledger, config_name=config_name)
        DBOS.register_instance(runtime)
        DBOS.launch()
        app.state.runtime = runtime
        app.state.ledger = ledger
        try:
            yield
        finally:
            DBOS.destroy()
            ledger.close()

    app = FastAPI(title="Faberon", version=__version__, lifespan=lifespan)
    _register_routes(app)
    return app


def create_app_slurm() -> FastAPI:
    """Uvicorn entrypoint: Slurm executor from the environment.

    Requires ``FABERON_DATABASE_URL`` and ``FABERON_SLURM_ACCOUNT``.
    Optional ``FABERON_SLURM_OUTPUT`` sets the Slurm ``--output`` path.
    """
    account = os.environ.get("FABERON_SLURM_ACCOUNT")
    if not account:
        raise RuntimeError("FABERON_SLURM_ACCOUNT is not set")
    executor = SlurmExecutor(
        account=account,
        output=os.environ.get("FABERON_SLURM_OUTPUT"),
    )
    return create_app(executor=executor)


def _register_routes(app: FastAPI) -> None:
    @app.post("/v0/campaigns", response_model=CampaignCreated, status_code=201)
    def create_campaign(body: CampaignCreate) -> CampaignCreated:
        runtime: Runtime = app.state.runtime
        ledger: Ledger = app.state.ledger
        campaign_id = uuid4()

        # A campaign is always created/initialized by a human
        ledger.append(
            Event(
                campaign_id=campaign_id,
                actor=Actor.HUMAN,
                type=EventType.CAMPAIGN_CREATED,
                justification="plan accepted",
                payload=body.plan.model_dump(mode="json"),
            )
        )

        setup = ExperimentSetup(
            campaign_id=campaign_id,
            command=body.command,
            submission_key=str(campaign_id),
            metric_command=body.plan.metric_command,
            metric_name=body.plan.metric_name,
            baseline=body.plan.baseline,
            poll_interval_seconds=body.poll_interval_seconds,
        )
        handle = DBOS.start_workflow(runtime.run_experiment, setup)
        return CampaignCreated(
            campaign_id=campaign_id,
            workflow_id=handle.workflow_id,
        )

    @app.get("/v0/campaigns/{campaign_id}", response_model=CampaignStatus)
    def get_campaign(campaign_id: UUID) -> CampaignStatus:
        ledger: Ledger = app.state.ledger
        events = [e for e in ledger.tail() if e.campaign_id == campaign_id]
        if not events:
            raise HTTPException(status_code=404, detail="campaign not found")
        return CampaignStatus(campaign_id=campaign_id, events=events)

    @app.get("/v0/events")
    async def stream_events(
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        ledger: Ledger = request.app.state.ledger

        async def generate() -> AsyncIterator[str]:
            cursor = after
            while True:
                if await request.is_disconnected():
                    break
                batch = list(ledger.tail(after=cursor))
                for event in batch:
                    assert event.seq is not None
                    cursor = event.seq
                    yield f"event: ledger\ndata: {event.model_dump_json()}\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
