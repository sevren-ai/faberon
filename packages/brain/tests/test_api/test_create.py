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

    # The campaign record carries the repo's branch and commit at creation.
    info = api.client.get(f"/v0/campaigns/{camp_id}").json()
    assert info["campaign"]["branch"] == "main"
    assert info["campaign"]["start_sha"] == start_sha

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


def test_detached_head(api: ApiFixture):
    """A repo on a detached HEAD has no branch for the campaign to commit on."""
    subprocess.run(
        ["git", "checkout", "HEAD~0"],
        cwd=api.repo_path,
        check=True,
        capture_output=True,
    )
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 409
    assert "detached" in response.json()["detail"]


def test_dirty_tree(api: ApiFixture):
    """Uncommitted changes to tracked files are rejected with guidance."""
    (Path(api.repo_path) / "train.py").write_text("work in progress\n")
    body = _create_body(str(uuid.uuid4()), api.repo_path)
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 409
    assert "commit or stash" in response.json()["detail"]

    # Restore the tree; an untracked file may stay.
    _git(api.repo_path, "checkout", "--", "train.py")
    (Path(api.repo_path) / "notes.txt").write_text("scratch\n")
    response = api.client.post("/v0/campaigns", json=body)
    assert response.status_code == 201
    DBOS.retrieve_workflow(response.json()["workflow_id"]).get_result()
    # The campaign's discards (reset --hard) left the untracked file alone.
    assert (Path(api.repo_path) / "notes.txt").exists()


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
    first = api.client.post(
        "/v0/campaigns",
        json=_create_body(str(uuid.uuid4()), api.repo_path),
    )
    assert first.status_code == 201
    first_id = first.json()["campaign_id"]

    # End the first campaign; the workflow completes and frees the repo.
    DBOS.retrieve_workflow(first.json()["workflow_id"]).get_result()
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
