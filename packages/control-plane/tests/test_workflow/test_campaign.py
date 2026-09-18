"""Campaign workflow tests: loop, hard caps, budget, cancel."""

import os
import uuid
from collections.abc import Iterator

import pytest
from dbos import DBOS, DBOSConfig

from faberon.ledger import Ledger
from faberon.schema.events import EventType, StopReason
from faberon.schema.plan import ResearchPlan
from faberon.workflow import CampaignRunner, CampaignSetup, Runtime

from .._fakes import FakeExecutor

pytestmark = pytest.mark.postgres

_DEFAULT_EXPERIMENTS = 3

_PLAN = {
    "goal": "Beat val_bpb baseline.",
    "metric_name": "val_bpb",
    "metric_command": "cat metric.txt",
    "baseline": 1.23,
    "budget_gpu_hours": 100.0,
    "max_experiments": _DEFAULT_EXPERIMENTS,
    "max_concurrency": 1,
    "walltime": 10,
    "stop_conditions": ["n/a"],
}


@pytest.fixture
def dbos() -> Iterator[None]:
    DBOS.destroy()
    config: DBOSConfig = {
        "name": "faberon-campaign-test",
        "system_database_url": os.environ["FABERON_DATABASE_URL"],
        "application_database_url": os.environ["FABERON_DATABASE_URL"],
        "run_admin_server": False,
        "log_level": "WARNING",
    }
    DBOS(config=config)
    DBOS.reset_system_database(truncate=True)
    connection = Ledger(os.environ["FABERON_DATABASE_URL"])._conn
    connection.execute("TRUNCATE events RESTART IDENTITY")
    connection.execute("TRUNCATE campaigns")
    yield
    DBOS.destroy()


def test_campaign_stops_on_max_experiments(dbos, repo, tmp_path):
    # Write dummy metric file
    path = tmp_path / f"metric-{uuid.uuid4().hex}.txt"
    path.write_text(f"val_bpb: {1.10}\n")
    # Create runtime with fake executor
    runtime = Runtime(
        FakeExecutor(elapsed_seconds=3600.0),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        repo_path=str(repo),
        edit_fn=lambda content: content + "# edit\n",
        target_file="train.py",
    )
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=ResearchPlan.model_validate(_PLAN),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.MAX_EXPERIMENTS.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail())
    ledger.close()
    types = [e.type for e in events]
    assert types.count(EventType.EXPERIMENT_PROPOSED) == _DEFAULT_EXPERIMENTS
    assert types.count(EventType.EXPERIMENT_JUDGED) == _DEFAULT_EXPERIMENTS
    assert types.count(EventType.CAMPAIGN_ENDED) == 1
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "max_experiments"


def test_campaign_stops_on_budget(dbos, repo, tmp_path):
    runtime = Runtime(
        FakeExecutor(elapsed_seconds=7200.0),  # 2 GPU-hours per job
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        repo_path=str(repo),
        edit_fn=lambda content: content + "# edit\n",
        target_file="train.py",
    )
    # TODO: copy instead of mutate
    new_plan = _PLAN
    new_plan["budget_gpu_hours"] = 7.0
    new_plan["max_experiments"] = 10.0
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=ResearchPlan.model_validate(new_plan),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.BUDGET_EXHAUSTED.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail())
    ledger.close()
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "budget_exhausted"
    # Each job burns 2 GPU-hours (7200 s x 1 GPU). After experiment 4 the
    # total is 8 >= budget 7, so the loop ends the campaign before the 5th.
    assert ended.payload["experiments_done"] == 4


def test_campaign_cancel_before_first_boundary(dbos, repo):
    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        repo_path=str(repo),
        edit_fn=lambda content: content,
        target_file="train.py",
    )
    campaign_id = uuid.uuid4()
    setup = CampaignSetup(
        campaign_id=campaign_id,
        plan=ResearchPlan.model_validate(_PLAN),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    # Start with the real workflow id (what the API layer does), then
    # signal it: send requires the workflow to exist.
    from dbos import SetWorkflowID

    with SetWorkflowID(str(campaign_id)):
        handle = DBOS.start_workflow(runner.run_campaign, setup)
    DBOS.send(str(campaign_id), "cancel", "cancel")
    stop_reason = handle.get_result()

    assert stop_reason == StopReason.CANCELLED.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = [e for e in ledger.tail() if e.campaign_id == campaign_id]
    ledger.close()
    assert list(dict.fromkeys(e.type for e in events)) == [EventType.CAMPAIGN_ENDED]
    ended = events[0]
    assert ended.payload["stop_reason"] == "cancelled"
    assert ended.actor.value == "human"
