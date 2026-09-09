"""Test running an experiment as a Slurm job.

Skipped unless ``FABERON_DATABASE_URL``, ``FABERON_SLURM_INTEGRATION=1``, and
``FABERON_SLURM_ACCOUNT`` are set. Run on the login node:

    FABERON_SLURM_INTEGRATION=1 uv run pytest -m slurm

This verifies the real ``SlurmExecutor`` path: sbatch submission, sacct poll
to completion, metric parse, judgment, and ledger recording.
"""

import os
import shlex
import uuid
from collections.abc import Iterator

import pytest
from dbos import DBOS, DBOSConfig

from faberon.executor.slurm import SlurmExecutor
from faberon.ledger import Ledger
from faberon.schema.events import EventType
from faberon.workflow import ExperimentSetup, Runtime

pytestmark = [pytest.mark.postgres, pytest.mark.slurm]


@pytest.fixture
def dbos() -> Iterator[None]:
    DBOS.destroy()
    config: DBOSConfig = {
        "name": "faberon-slurm-test",
        "system_database_url": os.environ["FABERON_DATABASE_URL"],
        "application_database_url": os.environ["FABERON_DATABASE_URL"],
        "run_admin_server": False,
        "log_level": "WARNING",
    }
    DBOS(config=config)
    DBOS.reset_system_database(truncate=True)
    connection = Ledger(os.environ["FABERON_DATABASE_URL"])._conn
    connection.execute("TRUNCATE events RESTART IDENTITY")
    yield
    DBOS.destroy()


def test_experiment_on_slurm(dbos, tmp_path):
    metric_file = tmp_path / "metric.txt"
    # The sbatch job writes the metric file; the workflow reads it back locally.
    command = [
        "sh",
        "-c",
        f"echo 'val_bpb: 1.10' > {shlex.quote(str(metric_file))}",
    ]
    executor = SlurmExecutor(
        account=os.environ["FABERON_SLURM_ACCOUNT"],
        output=str(tmp_path / "slurm-%j.out"),
    )
    ledger = Ledger(os.environ["FABERON_DATABASE_URL"])
    runtime = Runtime(executor, ledger, config_name=f"slurm-{uuid.uuid4().hex}")
    DBOS.register_instance(runtime)
    DBOS.launch()

    judgment = runtime.run_experiment(
        ExperimentSetup(
            campaign_id=uuid.UUID("00000000-0342-0342-0342-000000000000"),
            command=command,
            submission_key=f"slurm-{uuid.uuid4().hex}",
            metric_command=f"cat {metric_file}",
            metric_name="val_bpb",
            baseline=1.23,
            poll_interval_seconds=5.0,
        )
    )
    assert judgment == "keep"

    events = list(ledger.tail())
    ledger.close()
    types = [e.type for e in events]
    assert types == [EventType.EXPERIMENT_COMPLETED, EventType.EXPERIMENT_JUDGED]
