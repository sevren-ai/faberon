"""POST /v0/campaigns tests: creation, repo-state checks, conflicts.

Require Postgres (``postgres`` marker).
"""

import json
import subprocess
import uuid
from pathlib import Path

import pytest
from dbos import DBOS
from fastapi.testclient import TestClient

from faberon.api import create_app
from faberon.executor import JobState
from faberon.schema import EventType

from .._fakes import FakeExecutor
from ..conftest import make_repo
from .conftest import ApiFixture, _create_body, _git, _reset_databases

pytestmark = pytest.mark.postgres


def test_create_campaign(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    start_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=api.repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    response = api.client.post(
        "/v0/campaigns", json=_create_body(camp_id, api.repo_path)
    )
    assert response.status_code == 201
    body = response.json()
    assert "campaign_id" in body
    assert "workflow_id" in body

    handle = DBOS.retrieve_workflow(body["workflow_id"])
    stop_reason = handle.get_result()
    assert stop_reason == "max_experiments"
    assert api.executor.submit_count == 3

    # The campaign commits on its own fresh branch.
    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == f"faberon/{camp_id[:8]}"
    assert info["campaign"]["start_sha"] == start_sha
    assert _git(api.repo_path, "rev-parse", "main") == start_sha

    response = api.client.get(f"/v0/campaigns/{body['campaign_id']}/events.jsonl")
    types = [json.loads(line)["type"] for line in response.text.splitlines()]
    assert types[0] == EventType.CAMPAIGN_CREATED
    assert EventType.EXPERIMENT_COMPLETED in types
    assert EventType.EXPERIMENT_JUDGED in types


def test_outside_repo(api: ApiFixture):
    """A plan whose target_file escapes the repo is rejected before starting."""
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["plan"]["target_file"] = "../outside.py"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 422
    assert "inside the repo" in response.json()["detail"]


def test_absolute_target(api: ApiFixture):
    """An absolute target is rejected."""
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["plan"]["target_file"] = "/etc/cron.d/evil.py"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 422
    assert "relative path" in response.json()["detail"]


def test_non_repo(api: ApiFixture, tmp_path):
    """A repo path that is not a git repository is rejected at creation."""
    body = _create_body(str(uuid.uuid4()), str(tmp_path))
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 422


def test_empty_repo(api: ApiFixture, tmp_path):
    """A repo without a single commit has no HEAD to start a campaign from."""
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(str(empty), "init", "-b", "main")
    body = _create_body(str(uuid.uuid4()), str(empty))
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 409
    assert "no commits" in response.json()["detail"]


def test_detached_head(api: ApiFixture):
    """On a detached HEAD, the default branch is created at the current commit."""
    head = _git(api.repo_path, "rev-parse", "HEAD")
    _git(api.repo_path, "checkout", "HEAD~0")
    camp_id = str(uuid.uuid4())
    response = api.client.post(
        "/v0/campaigns", json=_create_body(camp_id, api.repo_path)
    )
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == f"faberon/{camp_id[:8]}"
    assert info["campaign"]["start_sha"] == head


def test_dirty_tree(api: ApiFixture):
    """Uncommitted changes to tracked files are rejected with guidance."""
    (Path(api.repo_path) / "train.py").write_text("work in progress\n")
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 409
    assert "commit or stash" in response.json()["detail"]

    # Restore the tree; an ignored untracked file may stay.
    _git(api.repo_path, "checkout", "--", "train.py")
    (Path(api.repo_path) / ".gitignore").write_text("notes.txt\n")
    _git(api.repo_path, "add", ".gitignore")
    _git(api.repo_path, "commit", "-m", "ignore notes")
    (Path(api.repo_path) / "notes.txt").write_text("scratch\n")
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()
    # The campaign's discards (reset --hard) left the ignored file alone.
    assert (Path(api.repo_path) / "notes.txt").exists()


def test_faberon_logs(api: ApiFixture):
    """Pre-existing .faberon run logs are declared disposable at creation."""
    log_dir = Path(api.repo_path) / ".faberon"
    log_dir.mkdir()
    (log_dir / "old-campaign:1.out").write_text("val_bpb: 1.10\n")
    response = api.client.post(
        "/v0/campaigns", json=_create_body(str(uuid.uuid4()), api.repo_path)
    )
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()
    exclude = Path(api.repo_path) / ".git" / "info" / "exclude"
    assert ".faberon/" in exclude.read_text().splitlines()


def test_untracked_tree(api: ApiFixture):
    """Untracked files not covered by .gitignore are rejected with guidance."""
    (Path(api.repo_path) / "helpers.py").write_text("x = 1\n")
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 409
    assert "untracked" in response.json()["detail"]

    # Ignoring the file unblocks creation.
    (Path(api.repo_path) / ".gitignore").write_text("helpers.py\n")
    _git(api.repo_path, "add", ".gitignore")
    # The .gitignore file must be committed
    _git(api.repo_path, "commit", "-m", "ignore helpers")
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()


def test_new_branch(api: ApiFixture):
    """A named branch that does not exist is created at the start commit."""
    head = _git(api.repo_path, "rev-parse", "HEAD")
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["branch"] = "exp-work"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    campaign_id = response.json()["campaign_id"]
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    info = api.client.get(f"/v0/campaigns/{campaign_id}").json()
    assert info["campaign"]["branch"] == "exp-work"
    assert info["campaign"]["start_sha"] == head
    # The campaign ran on its own branch; main was not touched.
    assert _git(api.repo_path, "symbolic-ref", "--short", "HEAD") == "exp-work"
    assert _git(api.repo_path, "rev-parse", "main") == head


def test_new_branch_detached(api: ApiFixture):
    """On a detached HEAD, a named branch is created at the current commit."""
    head = _git(api.repo_path, "rev-parse", "HEAD")
    _git(api.repo_path, "checkout", "HEAD~0")
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["branch"] = "work"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    campaign_id = response.json()["campaign_id"]
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    info = api.client.get(f"/v0/campaigns/{campaign_id}").json()
    assert info["campaign"]["branch"] == "work"
    assert info["campaign"]["start_sha"] == head
    # The campaign checked out its new branch.
    assert _git(api.repo_path, "symbolic-ref", "--short", "HEAD") == "work"


def test_existing_branch(api: ApiFixture):
    """An existing branch is adopted as-is: its tip is the start commit."""
    adopted_tip = _git(api.repo_path, "rev-parse", "HEAD")
    _git(api.repo_path, "branch", "adopted")
    # Move main one commit ahead so the tips differ.
    (Path(api.repo_path) / "train.py").write_text("main moves on\n")
    _git(api.repo_path, "add", "train.py")
    _git(api.repo_path, "commit", "-m", "main moves on")

    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["branch"] = "adopted"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    campaign_id = response.json()["campaign_id"]
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()

    info = api.client.get(f"/v0/campaigns/{campaign_id}").json()
    assert info["campaign"]["branch"] == "adopted"
    assert info["campaign"]["start_sha"] == adopted_tip
    assert _git(api.repo_path, "symbolic-ref", "--short", "HEAD") == "adopted"


def test_checkout_failure(api: ApiFixture):
    """A failed checkout rejects creation; no campaign is recorded."""
    # A stale index lock passes the clean-tree checks but blocks checkout.
    (Path(api.repo_path) / ".git" / "index.lock").write_text("")
    camp_id = str(uuid.uuid4())
    response = api.client.post(
        "/v0/campaigns", json=_create_body(camp_id, api.repo_path)
    )
    assert response.status_code == 422
    assert "index.lock" in response.json()["detail"]
    assert api.client.get(f"/v0/campaigns/{camp_id}").status_code == 404


def test_invalid_branch(api: ApiFixture):
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    body["branch"] = "no..dots"
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 422


def test_create_campaign_idempotent(api: ApiFixture):
    camp_id = str(uuid.uuid4())
    body = _create_body(camp_id, api.repo_path)
    first = api.client.post("/v0/campaigns", json=body)
    assert first.status_code == 201
    DBOS.retrieve_workflow(first.json()["workflow_id"]).get_result()

    # Retry with the same campaign_id: no duplicate workflow, no duplicate event.
    second = api.client.post("/v0/campaigns", json=body)
    assert second.status_code == 201
    assert second.json()["campaign_id"] == first.json()["campaign_id"]
    assert second.json()["workflow_id"] == first.json()["workflow_id"]
    assert api.executor.submit_count == 3

    status = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    types = [json.loads(line)["type"] for line in status.text.splitlines()]
    assert types.count(EventType.CAMPAIGN_CREATED) == 1


def test_second_campaign_rejected(tmp_path, repo):
    """While one campaign is active on a repo, a second one is rejected."""
    DBOS.destroy()

    executor = FakeExecutor(JobState.RUNNING)
    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )
    _reset_databases()
    with TestClient(app) as client:
        first = client.post(
            "/v0/campaigns",
            json=_create_body(str(uuid.uuid4()), str(repo)),
        )
        assert first.status_code == 201

        # The running campaign reads active.
        info = client.get(f"/v0/campaigns/{first.json()['campaign_id']}").json()
        assert info["status"] == "active"
        assert info["stop_reason"] is None

        conflict = client.post(
            "/v0/campaigns",
            json=_create_body(str(uuid.uuid4()), str(repo)),
        )
        assert conflict.status_code == 409
        assert first.json()["campaign_id"] in conflict.json()["detail"]

        # A different repo path is unaffected.
        (tmp_path / "other-repo").mkdir()
        other = make_repo(tmp_path / "other-repo")
        accepted = client.post(
            "/v0/campaigns",
            json=_create_body(str(uuid.uuid4()), str(other)),
        )
        assert accepted.status_code == 201
    DBOS.destroy()


def test_no_conflict_with_ended_campaigns(api: ApiFixture):
    """Once the campaign on a repo ends, a new one on the same repo is accepted."""
    first_id = str(uuid.uuid4())
    _run_campaign(api, first_id)

    info = api.client.get(f"/v0/campaigns/{first_id}").json()
    assert info["status"] == "ended"
    events = api.client.get(f"/v0/campaigns/{first_id}/events.jsonl")
    types = [json.loads(line)["type"] for line in events.text.splitlines()]
    assert EventType.CAMPAIGN_ENDED in types

    # Submit the second: should be no issue
    second = api.client.post(
        "/v0/campaigns",
        json=_create_body(str(uuid.uuid4()), api.repo_path),
    )
    assert second.status_code == 201


def _run_campaign(
    api: ApiFixture, camp_id: str, *, keep_metric: str | None = None
) -> None:
    """Create a campaign and wait for it to end.

    With ``keep_metric``, the first experiment's log is pre-written so it is
    kept; the rest discard (their logs stay empty).
    """
    if keep_metric is not None:
        out = Path(api.repo_path) / ".faberon" / f"{camp_id}:1.out"
        out.parent.mkdir(exist_ok=True)
        out.write_text(f"val_bpb: {keep_metric}\n")
    response = api.client.post(
        "/v0/campaigns", json=_create_body(camp_id, api.repo_path)
    )
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()


def _successor_body(**overrides) -> dict:
    """A successor body; tests override what they exercise."""
    body = {
        "campaign_id": str(uuid.uuid4()),
        "budget_gpu_hours": 5.0,
        "max_experiments": 2,
    }
    body.update(overrides)
    return body


def _create_successor(api: ApiFixture, pred_id: str, **overrides) -> str:
    """Create a successor and wait for it to end. Return its campaign id."""
    body = _successor_body(**overrides)
    response = api.client.post(f"/v0/campaigns/{pred_id}/successor", json=body)
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()
    return body["campaign_id"]


def test_successor(api: ApiFixture):
    """A successor starts at the predecessor's best kept commit."""
    pred_id = str(uuid.uuid4())
    _run_campaign(api, pred_id, keep_metric="1.10")
    # Experiments 2 and 3 discarded, so the predecessor's branch rests at the
    # kept commit.
    keep_sha = _git(api.repo_path, "rev-parse", f"faberon/{pred_id[:8]}")

    camp_id = _create_successor(api, pred_id)

    branch = f"faberon/{camp_id[:8]}"
    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == branch
    assert info["campaign"]["start_sha"] == keep_sha
    # The derived plan: fresh budget and limits, baseline reseeded from the
    # predecessor's best kept metric.
    plan = info["campaign"]["plan"]
    assert plan["budget_gpu_hours"] == 5.0
    assert plan["max_experiments"] == 2
    assert plan["baseline"] == 1.10
    assert info["campaign"]["poll_interval_seconds"] == 0.05
    # Only the derived limits ran: 3 predecessor + 2 successor experiments.
    assert api.executor.submit_count == 5
    # The successor's experiments all discarded: the branch rests at the
    # succession commit, and the repo is on the new branch.
    assert _git(api.repo_path, "rev-parse", branch) == keep_sha
    assert _git(api.repo_path, "symbolic-ref", "--short", "HEAD") == branch

    events = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    parsed = [json.loads(line) for line in events.text.splitlines()]
    assert parsed[0]["type"] == EventType.CAMPAIGN_CREATED
    assert parsed[0]["payload"]["predecessor"] == {
        "campaign_id": pred_id,
        "sha": keep_sha,
    }
    # The first experiment built on the succession commit.
    proposed = next(e for e in parsed if e["type"] == EventType.EXPERIMENT_PROPOSED)
    assert proposed["payload"]["parent_sha"] == keep_sha


def test_successor_no_keeps(api: ApiFixture):
    """Without keeps, the successor starts at the predecessor's start commit."""
    base_sha = _git(api.repo_path, "rev-parse", "HEAD")
    pred_id = str(uuid.uuid4())
    _run_campaign(api, pred_id)

    camp_id = _create_successor(api, pred_id)

    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["start_sha"] == base_sha
    # No kept metric to reseed from: the predecessor's baseline stands.
    assert info["campaign"]["plan"]["baseline"] == 1.23
    events = api.client.get(f"/v0/campaigns/{camp_id}/events.jsonl")
    created = json.loads(events.text.splitlines()[0])
    assert created["payload"]["predecessor"] == {
        "campaign_id": pred_id,
        "sha": base_sha,
    }


def test_successor_limits(api: ApiFixture):
    """The brain does not guess a budget: explicit limits are required."""
    pred_id = str(uuid.uuid4())
    _run_campaign(api, pred_id)

    body = {"campaign_id": str(uuid.uuid4())}
    response = api.client.post(f"/v0/campaigns/{pred_id}/successor", json=body)
    assert response.status_code == 422


def test_predecessor_unknown(api: ApiFixture):
    """Check that a successor call with an unknown predecessor ID fails."""
    response = api.client.post(
        f"/v0/campaigns/{uuid.uuid4()}/successor", json=_successor_body()
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_predecessor_active(tmp_path, repo):
    """A still-active predecessor is rejected with guidance."""
    DBOS.destroy()

    executor = FakeExecutor(JobState.RUNNING)
    app = create_app(
        executor=executor,
        config_name=f"api-test-{uuid.uuid4().hex}",
    )
    _reset_databases()
    with TestClient(app) as client:
        first = client.post(
            "/v0/campaigns",
            json=_create_body(str(uuid.uuid4()), str(repo)),
        )
        assert first.status_code == 201
        info = client.get(f"/v0/campaigns/{first.json()['campaign_id']}").json()
        assert info["status"] == "active"

        conflict = client.post(
            f"/v0/campaigns/{first.json()['campaign_id']}/successor",
            json={
                "campaign_id": str(uuid.uuid4()),
                "budget_gpu_hours": 5.0,
                "max_experiments": 2,
            },
        )
        assert conflict.status_code == 409
        assert "still active" in conflict.json()["detail"]
    DBOS.destroy()


def test_successor_branches(api: ApiFixture):
    """Branch handling for successors: create, reject strays, adopt at sha."""
    pred_id = str(uuid.uuid4())
    _run_campaign(api, pred_id, keep_metric="1.10")
    keep_sha = _git(api.repo_path, "rev-parse", f"faberon/{pred_id[:8]}")

    # A named branch that does not exist is created at the succession sha.
    camp_id = _create_successor(api, pred_id, branch="successor-work")
    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == "successor-work"
    assert info["campaign"]["start_sha"] == keep_sha
    assert _git(api.repo_path, "rev-parse", "successor-work") == keep_sha

    # An existing branch at another commit is rejected: adopting it would
    # strand commits.
    _git(api.repo_path, "branch", "stray", "main")
    body = _successor_body(branch="stray")
    response = api.client.post(f"/v0/campaigns/{pred_id}/successor", json=body)
    assert response.status_code == 409
    assert "strand" in response.json()["detail"]

    # An existing branch already at the succession sha is adopted as-is.
    _git(api.repo_path, "branch", "at-succession", keep_sha)
    camp_id = _create_successor(api, pred_id, branch="at-succession")
    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == "at-succession"
    assert info["campaign"]["start_sha"] == keep_sha
