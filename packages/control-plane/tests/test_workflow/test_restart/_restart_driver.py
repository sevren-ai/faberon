"""Subprocess driver for the kill-mid-run restart test.

Run in two modes:

- ``start``: initialise DBOS on a clean system database, register the
  runtime, start ``run_experiment`` with a fixed workflow id, then stay
  alive so the workflow is mid-poll when the parent kills the process.
- ``recover``: initialise DBOS without resetting the system database,
  register the runtime, launch (which recovers the pending workflow), wait
  for it to finish, and print the judgment.

State that crosses the process boundary lives in files: the fake
executor's job state in ``FABERON_TEST_EXECUTOR_DIR``, the metric output
in ``FABERON_TEST_RUN_DIR``, and the workflow and event state in Postgres.
The runtime instance uses a fixed ``config_name`` so the recovering
process can re-register an instance under the same name and DBOS can
route the recovered workflow to it.
"""

import os
import sys
import time
from uuid import UUID

from dbos import DBOS, DBOSConfig, SetWorkflowID

from faberon.ledger import Ledger
from faberon.workflow import Runtime

from ._fake_file_executor import FakeFileExecutor


def _config() -> DBOSConfig:
    return {
        "name": "faberon-test",
        "system_database_url": os.environ["FABERON_DATABASE_URL"],
        "application_database_url": os.environ["FABERON_DATABASE_URL"],
        "run_admin_server": False,
        "log_level": "WARNING",
    }


def _make_runtime() -> Runtime:
    runtime = Runtime(
        FakeFileExecutor(os.environ["FABERON_TEST_EXECUTOR_DIR"]),
        Ledger(os.environ["FABERON_DATABASE_URL"]),
        config_name="default",
    )
    DBOS.register_instance(runtime)
    return runtime


def _experiment_args() -> dict:
    return {
        "campaign_id": UUID(os.environ["FABERON_TEST_CAMPAIGN_ID"]),
        "command": ["sleep", "30"],
        "submission_key": os.environ["FABERON_TEST_WF_ID"],
        "metric_command": f"cat {os.environ['FABERON_TEST_RUN_DIR']}/metric.txt",
        "metric_name": "val_bpb",
        "baseline": 1.23,
        "poll_interval_seconds": 0.05,
    }


def _start() -> None:
    DBOS(config=_config())
    DBOS.reset_system_database(truncate=True)
    runtime = _make_runtime()
    DBOS.launch()
    # Clean slate for the events table.
    Ledger(os.environ["FABERON_DATABASE_URL"])._conn.execute(
        "TRUNCATE events RESTART IDENTITY"
    )
    with SetWorkflowID(os.environ["FABERON_TEST_WF_ID"]):
        DBOS.start_workflow(runtime.run_experiment, **_experiment_args())
    # Stay alive so the parent can kill us mid-poll.
    while True:
        time.sleep(1)


def _recover() -> None:
    DBOS(config=_config())
    _make_runtime()
    DBOS.launch()  # recovers the pending workflow
    handle = DBOS.retrieve_workflow(os.environ["FABERON_TEST_WF_ID"])
    result = handle.get_result()
    print("JUDGMENT:", result, flush=True)
    DBOS.destroy()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "start":
        _start()
    elif mode == "recover":
        _recover()
    else:
        raise SystemExit(f"unknown mode: {mode!r}; expected start|recover")


if __name__ == "__main__":
    main()
