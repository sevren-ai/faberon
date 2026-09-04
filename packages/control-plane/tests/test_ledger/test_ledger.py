"""Tests for the Postgres-backed ledger. Requires a real Postgres."""

import os
import uuid
from collections.abc import Iterator

import pytest

from faberon.ledger import Ledger
from faberon.schema.events import Actor, Event, EventType

pytestmark = pytest.mark.skipif(
    not os.environ.get("FABERON_DATABASE_URL"),
    reason="set FABERON_DATABASE_URL to a Postgres instance to run ledger tests",
)


@pytest.fixture
def ledger() -> Iterator[Ledger]:
    db = Ledger(os.environ["FABERON_DATABASE_URL"])
    # Test isolation: start each test from an empty log at seq 1.
    db._conn.execute("TRUNCATE events RESTART IDENTITY")
    yield db
    db.close()


def _event(**overrides) -> Event:
    return Event(
        campaign_id=overrides.get("campaign_id", uuid.uuid4()),
        actor=overrides.get("actor", Actor.AGENT),
        type=overrides.get("type", EventType.CAMPAIGN_CREATED),
        justification=overrides.get("justification", "test"),
        payload=overrides.get("payload", {}),
    )


def test_append_assigns_seq(ledger):
    event = _event()
    stored = ledger.append(event)
    assert stored.seq == 1
    assert stored.ts == event.ts
    assert stored.campaign_id == event.campaign_id


def test_tail_orders_by_seq(ledger):
    first = ledger.append(_event())
    second = ledger.append(_event())
    events = list(ledger.tail())
    assert [e.seq for e in events] == [first.seq, second.seq]


def test_tail_after_cursor(ledger):
    first = ledger.append(_event())
    ledger.append(_event())
    assert first.seq is not None
    rest = list(ledger.tail(after=first.seq))
    assert [e.seq for e in rest] == [2]


def test_append_preserves_fields(ledger):
    event = _event(justification="plan accepted", payload={"k": "v"})
    stored = ledger.append(event)
    again = next(ledger.tail())
    assert again == stored
    assert again.justification == "plan accepted"
    assert again.payload == {"k": "v"}
