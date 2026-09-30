"""Campaign workflow tests: loop, hard caps, budget, cancel."""

import os
import subprocess
import uuid
from collections.abc import Iterator

import pytest
from dbos import DBOS, DBOSConfig
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UserError

from faberon.ledger import Ledger
from faberon.schema import EventType, ResearchPlan, StopReason
from faberon.workflow import CampaignRunner, CampaignSetup, Runtime
from faberon.workflow.campaign import MAX_PROP_FAILS
from faberon.workflow.models import Proposal

from .._fakes import FakeExecutor, FakeProposer
from ..conftest import make_plan

pytestmark = pytest.mark.postgres


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
        proposer=FakeProposer(),
    )
    plan = make_plan()
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=plan,
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.MAX_EXPERIMENTS.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(setup.campaign_id))
    ledger.close()
    types = [e.type for e in events]
    assert types.count(EventType.EXPERIMENT_PROPOSED) == plan.max_experiments
    assert types.count(EventType.EXPERIMENT_JUDGED) == plan.max_experiments
    assert types.count(EventType.EXPERIMENT_DESIGNING) == plan.max_experiments
    assert types.count(EventType.CAMPAIGN_ENDED) == 1
    proposed = next(e for e in events if e.type == EventType.EXPERIMENT_PROPOSED)
    assert proposed.justification == "rationale for test proposal 1"
    assert proposed.payload["title"] == "test proposal 1"
    # completed/judged carry the same index and sha as their proposal.
    proposed_by_index = {
        e.payload["index"]: e.payload["sha"]
        for e in events
        if e.type == EventType.EXPERIMENT_PROPOSED
    }
    judged = [e for e in events if e.type == EventType.EXPERIMENT_JUDGED]
    assert [e.payload["index"] for e in judged] == sorted(proposed_by_index)
    assert all(
        e.payload["sha"] == proposed_by_index[e.payload["index"]] for e in judged
    )
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "max_experiments"


def test_campaign_commit_msg(dbos, repo, tmp_path):
    """Experiment commits are titled ``exp N: <proposal title>``."""
    # One metric file per job id, each better than the last, so both
    # experiments keep and their commits stay on the branch.
    (tmp_path / "metric-fake-1.txt").write_text("val_bpb: 1.10\n")
    (tmp_path / "metric-fake-2.txt").write_text("val_bpb: 1.00\n")
    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        proposer=FakeProposer(),
    )
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=make_plan(
            metric_command=f"cat {tmp_path}/metric-{{job_id}}.txt",
            max_experiments=2,
        ),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.MAX_EXPERIMENTS.value
    log = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    # Newest first; both experiments keep, so nothing is reset away.
    assert log[0] == "exp 2: test proposal 2"
    assert log[1] == "exp 1: test proposal 1"


def test_proposal_title_max_length():
    """A title over 55 characters is rejected at the model boundary."""
    with pytest.raises(ValidationError):
        Proposal(content="print('x')\n", title="x" * 56, rationale="a rationale")


def test_campaign_survives_failed_proposer(dbos, repo, tmp_path):
    """A failed propose step is recorded and skipped, not fatal and not counted."""
    (tmp_path / "metric-fake-1.txt").write_text("val_bpb: 1.10\n")
    (tmp_path / "metric-fake-2.txt").write_text("val_bpb: 1.00\n")

    class FlakyProposer(FakeProposer):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def propose(
            self,
            campaign_id: uuid.UUID,
            plan: ResearchPlan,
            current_content: str,
        ) -> Proposal:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("proposer call exceeded 600 seconds")
            if self.calls == 3:
                raise UnexpectedModelBehavior("maximum output retries")
            if self.calls == 4:
                raise ModelHTTPError(503, "test-model", body="overloaded")
            return super().propose(campaign_id, plan, current_content)

    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    proposer = FlakyProposer()
    runner = CampaignRunner(runtime, proposer=proposer)
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=make_plan(
            metric_command=f"cat {tmp_path}/metric-{{job_id}}.txt",
            max_experiments=2,
        ),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.MAX_EXPERIMENTS.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(setup.campaign_id))
    ledger.close()
    # started designing 5 times, 3 of which failed
    assert proposer.calls == 5
    designed = [e for e in events if e.type == EventType.EXPERIMENT_DESIGNING]
    assert len(designed) == 5
    failed = [e for e in events if e.type == EventType.EXPERIMENT_PROPOSE_FAILED]
    assert [e.payload["error"] for e in failed] == [
        "TimeoutError",
        "UnexpectedModelBehavior",
        "ModelHTTPError",
    ]
    # proposed and ran 2 experiments succesfully
    proposed = [e for e in events if e.type == EventType.EXPERIMENT_PROPOSED]
    assert [e.payload["index"] for e in proposed] == [1, 2]
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["experiments_done"] == 2


def test_campaign_ends_max_propose_failure(dbos, repo, tmp_path):
    """A proposer that fails on every call ends the campaign with 'error'."""

    class AlwaysFailProposer(FakeProposer):
        def propose(
            self,
            campaign_id: uuid.UUID,
            plan: ResearchPlan,
            current_content: str,
        ) -> Proposal:
            raise TimeoutError("proposer call exceeded 600 seconds")

    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(runtime, proposer=AlwaysFailProposer())
    campaign_id = uuid.uuid4()
    setup = CampaignSetup(
        campaign_id=campaign_id,
        plan=make_plan(),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.ERROR.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(campaign_id))
    ledger.close()
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "error"
    assert ended.payload["experiments_done"] == 0
    failed = [e for e in events if e.type == EventType.EXPERIMENT_PROPOSE_FAILED]
    assert len(failed) == MAX_PROP_FAILS
    # No experiment ever ran: no proposals, no submissions.
    assert not [e for e in events if e.type == EventType.EXPERIMENT_PROPOSED]
    assert not [e for e in events if e.type == EventType.EXPERIMENT_SUBMITTED]


def test_campaign_dies_on_misconfiguration(dbos, repo, tmp_path):
    """A UserError kills the campaign and records a terminal 'error' event."""

    class BrokenProposer(FakeProposer):
        def propose(
            self,
            campaign_id: uuid.UUID,
            plan: ResearchPlan,
            current_content: str,
        ) -> Proposal:
            raise UserError("bad model string")

    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(runtime, proposer=BrokenProposer())
    campaign_id = uuid.uuid4()
    setup = CampaignSetup(
        campaign_id=campaign_id,
        plan=make_plan(max_experiments=1),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    with pytest.raises(UserError):
        runner.run_campaign(setup)

    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(campaign_id))
    ledger.close()
    crashed = next(e for e in events if e.type == EventType.CAMPAIGN_CRASHED)
    assert crashed.payload["error"] == "UserError"
    assert "bad model string" in crashed.justification
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "error"


def test_campaign_stops_on_budget(dbos, repo, tmp_path):
    runtime = Runtime(
        FakeExecutor(elapsed_seconds=7200.0),  # 2 GPU-hours per job
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        proposer=FakeProposer(),
    )
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=make_plan(budget_gpu_hours=7.0, max_experiments=10),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.BUDGET_EXHAUSTED.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(setup.campaign_id))
    ledger.close()
    ended = next(e for e in events if e.type == EventType.CAMPAIGN_ENDED)
    assert ended.payload["stop_reason"] == "budget_exhausted"
    # Each job burns 2 GPU-hours (7200 s x 1 GPU). After experiment 4 the
    # total is 8 >= budget 7, so the loop ends the campaign before the 5th.
    assert ended.payload["experiments_done"] == 4


def test_campaign_metric_command_renders_job_id(dbos, repo, tmp_path):
    # The metric file is named after the executor's job id: only a rendered
    # {job_id} placeholder finds it.
    (tmp_path / "metric-fake-1.txt").write_text("val_bpb: 1.10\n")
    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        proposer=FakeProposer(),
    )
    setup = CampaignSetup(
        campaign_id=uuid.uuid4(),
        plan=make_plan(
            metric_command=f"cat {tmp_path}/metric-{{job_id}}.txt",
            max_experiments=1,
        ),
        command=["true"],
        poll_interval_seconds=0.05,
        repo_path=str(repo),
        target_file="train.py",
    )
    DBOS.launch()

    stop_reason = runner.run_campaign(setup)

    assert stop_reason == StopReason.MAX_EXPERIMENTS.value
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    events = list(ledger.tail(setup.campaign_id))
    ledger.close()
    judged = next(e for e in events if e.type == EventType.EXPERIMENT_JUDGED)
    assert judged.payload["judgment"] == "keep"
    assert judged.payload["metric_value"] == 1.10
    assert judged.payload["index"] == 1


def test_campaign_ends_on_cancel(dbos, repo):
    """A cancelled campaign ends with stop_reason ``cancelled`` by the human."""
    runtime = Runtime(
        FakeExecutor(),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name=f"campaign-{uuid.uuid4().hex}",
    )
    DBOS.register_instance(runtime)
    runner = CampaignRunner(
        runtime,
        proposer=FakeProposer(),
    )
    campaign_id = uuid.uuid4()
    setup = CampaignSetup(
        campaign_id=campaign_id,
        plan=make_plan(),
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
    events = list(ledger.tail(campaign_id))
    ledger.close()
    ended = events[-1]
    assert ended.type == EventType.CAMPAIGN_ENDED
    assert ended.payload["stop_reason"] == "cancelled"
    assert ended.actor.value == "human"
