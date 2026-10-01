"""Tests for the Postgres-backed ledger. Requires a real Postgres."""

import os
import uuid
from collections.abc import Iterator

import pytest

from faberon.ledger import Ledger
from faberon.schema import Actor, Event, EventType

from ..conftest import make_plan

pytestmark = pytest.mark.postgres


@pytest.fixture
def ledger() -> Iterator[Ledger]:
    db = Ledger(os.environ["FABERON_DATABASE_URL"])
    # Test isolation: start each test from an empty log at seq 1.
    db._conn.execute("TRUNCATE events RESTART IDENTITY")
    db._conn.execute("TRUNCATE campaigns")
    yield db
    db.close()


def _event(**overrides) -> Event:
    return Event(
        campaign_id=overrides.get("campaign_id", uuid.uuid4()),
        actor=overrides.get("actor", Actor.AGENT),
        type=overrides.get("type", EventType.CAMPAIGN_CREATED),
        reason=overrides.get("reason", "test event"),
        payload=overrides.get("payload", {}),
    )


def test_append_assigns_seq(ledger):
    event = _event()
    stored = ledger.append(event)
    assert stored.seq == 1
    assert stored.ts == event.ts
    assert stored.campaign_id == event.campaign_id


def test_tail_orders_by_seq(ledger):
    camp_id = uuid.uuid4()
    first = ledger.append(_event(campaign_id=camp_id))
    second = ledger.append(_event(campaign_id=camp_id))
    events = list(ledger.tail(camp_id))
    assert [e.seq for e in events] == [first.seq, second.seq]


def test_tail_after_cursor(ledger):
    camp_id = uuid.uuid4()
    first = ledger.append(_event(campaign_id=camp_id))
    ledger.append(_event(campaign_id=camp_id))
    assert first.seq is not None
    rest = list(ledger.tail(camp_id, after=first.seq))
    assert [e.seq for e in rest] == [2]


def test_tail_scopes_to_campaign(ledger):
    camp_id = uuid.uuid4()
    ledger.append(_event(campaign_id=camp_id))
    ledger.append(_event())
    assert [e.campaign_id for e in ledger.tail(camp_id)] == [camp_id]


def test_append_preserves_fields(ledger):
    event = _event(reason="plan accepted", payload={"k": "v"})
    stored = ledger.append(event)
    again = next(ledger.tail(stored.campaign_id))
    assert again == stored
    assert again.reason == "plan accepted"
    assert again.payload == {"k": "v"}


def test_get_campaign(ledger):
    camp_id = uuid.uuid4()
    assert ledger.get_campaign(camp_id) is None
    plan = make_plan()
    ledger.create_campaign(camp_id, str(camp_id), plan, "/repo/a", 30.0)
    campaign = ledger.get_campaign(camp_id)
    assert campaign is not None
    assert campaign.campaign_id == camp_id
    assert campaign.workflow_id == str(camp_id)
    assert campaign.plan == plan
    assert campaign.repo_path == "/repo/a"
    assert campaign.poll_interval_seconds == 30.0


def test_list_campaigns(ledger):
    assert ledger.list_campaigns() == []
    camp_a = uuid.uuid4()
    camp_b = uuid.uuid4()
    ledger.create_campaign(camp_a, str(camp_a), make_plan(), "/repo/a", 30.0)
    ledger.create_campaign(camp_b, str(camp_b), make_plan(), "/repo/b", 30.0)
    campaigns = ledger.list_campaigns()
    assert [c.campaign_id for c in campaigns] == [camp_a, camp_b]


def test_create_campaign_idempotent(ledger):
    camp_id = uuid.uuid4()
    plan = make_plan()
    assert ledger.create_campaign(camp_id, str(camp_id), plan, "/repo/a", 30.0) is True
    assert ledger.create_campaign(camp_id, str(camp_id), plan, "/repo/a", 30.0) is False
    events = list(ledger.tail(camp_id))
    assert len(events) == 1
    assert events[0].type == EventType.CAMPAIGN_CREATED


def test_campaigns_on_repo(ledger):
    repo = "/repo/a"
    assert ledger.campaigns_on_repo(repo) == []

    camp_id = uuid.uuid4()
    ledger.create_campaign(camp_id, str(camp_id), make_plan(), repo, 30.0)
    # A different repo is not affected.
    assert ledger.campaigns_on_repo("/repo/other") == []
    campaigns = ledger.campaigns_on_repo(repo)
    assert [c.campaign_id for c in campaigns] == [camp_id]


def test_campaign_events(ledger):
    camp_a = uuid.uuid4()
    camp_b = uuid.uuid4()
    ledger.append(_event(campaign_id=camp_a))
    ledger.append(_event(campaign_id=camp_b))
    ledger.append(_event(campaign_id=camp_a))

    a_events = ledger.campaign_events(camp_a)
    assert [e.campaign_id for e in a_events] == [camp_a, camp_a]
    assert [e.seq for e in a_events] == [1, 3]
    assert len(ledger.campaign_events(camp_b)) == 1
    assert ledger.campaign_events(uuid.uuid4()) == []
