"""Test running an experiment as a Slurm job.

Skipped unless Postgres is reachable, ``slurm_account`` is in the config
file, and ``FABERON_SLURM_INTEGRATION=1`` is set. Run on the login node:

    FABERON_SLURM_INTEGRATION=1 uv run pytest -m slurm

This verifies the real ``SlurmExecutor`` path: sbatch submission, sacct poll
to completion, metric parse, judgment, and ledger recording.
"""

import uuid
from collections.abc import Iterator

import pytest
from dbos import DBOS, DBOSConfig

from faberon import config as faberon_config
from faberon.executor.slurm import SlurmExecutor
from faberon.ledger import Ledger
from faberon.schema import EventType
from faberon.workflow import ExperimentSetup, Runtime

pytestmark = [pytest.mark.postgres, pytest.mark.slurm]


@pytest.fixture
def dbos() -> Iterator[None]:
    DBOS.destroy()
    db_url = faberon_config.database_url()
    config: DBOSConfig = {
        "name": "faberon-slurm-test",
        "system_database_url": db_url,
        "application_database_url": db_url,
        "run_admin_server": False,
        "log_level": "WARNING",
    }
    DBOS(config=config)
    DBOS.reset_system_database(truncate=True)
    connection = Ledger(db_url)._conn
    connection.execute("TRUNCATE events RESTART IDENTITY")
    yield
    DBOS.destroy()


def test_experiment_on_slurm(dbos, tmp_path):
    # The job prints the metric to stdout, which lands in the job log at
    # {repo}/.faberon/{submission_key}.out; the workflow parses it from there.
    command = "echo 'val_bpb: 1.10'"
    submission_key = f"slurm-{uuid.uuid4().hex}"
    account = faberon_config.slurm_account()
    assert account is not None
    executor = SlurmExecutor(
        account=account,
        max_walltime=10,
    )
    ledger = Ledger(faberon_config.database_url())
    runtime = Runtime(executor, ledger, config_name=f"slurm-{uuid.uuid4().hex}")
    DBOS.register_instance(runtime)
    DBOS.launch()

    campaign_id = uuid.UUID("00000000-0342-0342-0342-000000000000")
    judgment = runtime.run_experiment(
        ExperimentSetup(
            campaign_id=campaign_id,
            command=command,
            submission_key=submission_key,
            metric="val_bpb",
            repo_path=str(tmp_path),
            baseline=1.23,
            poll_interval_seconds=5.0,
            walltime=10,
            index=1,
            sha="0" * 40,
        )
    )
    assert judgment.judgment == "keep"

    events = list(ledger.tail(campaign_id))
    ledger.close()
    types = [e.type for e in events]
    assert types == [
        EventType.EXPERIMENT_SUBMITTED,
        EventType.EXPERIMENT_COMPLETED,
        EventType.EXPERIMENT_JUDGED,
    ]
