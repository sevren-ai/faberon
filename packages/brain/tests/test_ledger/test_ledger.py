"""Tests for the Postgres-backed ledger. Requires a real Postgres."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from faberon import config
from faberon.ledger import SCHEMA_VERSION, Ledger, SchemaError, ensure_schema
from faberon.ledger import ledger as ledger_module
from faberon.ledger.ledger import _CREATE_SCHEMA_VERSION
from faberon.schema import Actor, Event, EventType, Predecessor

from ..conftest import make_plan

pytestmark = pytest.mark.postgres


@pytest.fixture
def ledger() -> Iterator[Ledger]:
    db = Ledger(config.database_url())
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


def test_schema_fresh_database(ledger):
    """A fresh database gets the schema and the current version stamp."""
    row = ledger._conn.execute("SELECT version FROM schema_version").fetchone()
    assert row == (SCHEMA_VERSION,)


def test_schema_wrong_version(ledger):
    """A stamp from another release is rejected, not silently used."""
    ledger._conn.execute("UPDATE schema_version SET version = 999")
    try:
        with pytest.raises(SchemaError, match="999"):
            ensure_schema(ledger._conn)
    finally:
        ledger._conn.execute(
            "UPDATE schema_version SET version = %s", (SCHEMA_VERSION,)
        )


def _restore_stamp(ledger, version: int = SCHEMA_VERSION) -> None:
    ledger._conn.execute("UPDATE schema_version SET version = %s", (version,))


def _campaigns_columns(ledger) -> set[str]:
    rows = ledger._conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'campaigns'"
    )
    return {row[0] for row in rows}


def test_reject_outdated_version(ledger):
    """An outdated stamp is rejected when migration is not requested."""
    ledger._conn.execute("UPDATE schema_version SET version = 0")
    try:
        with pytest.raises(SchemaError, match="version 0"):
            ensure_schema(ledger._conn)
    finally:
        _restore_stamp(ledger)


def test_missing_migration(ledger):
    """A version with no migration path fails without touching the database."""
    ledger._conn.execute("UPDATE schema_version SET version = 0")
    try:
        with pytest.raises(SchemaError, match="no migration from schema version 0"):
            ensure_schema(ledger._conn, migrate=True)
        row = ledger._conn.execute("SELECT version FROM schema_version").fetchone()
        assert row == (0,)
    finally:
        _restore_stamp(ledger)


def test_migration(
    ledger, monkeypatch: pytest.MonkeyPatch
):
    """An outdated database migrates step by step and keeps its rows."""
    camp_id = uuid.uuid4()
    ledger.create_campaign(
        camp_id,
        str(camp_id),
        make_plan(),
        "/repo/a",
        30.0,
        branch="main",
        start_sha="a",
    )
    monkeypatch.setattr(ledger_module, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(
        ledger_module,
        "_MIGRATIONS",
        {1: ["ALTER TABLE campaigns ADD COLUMN migration_probe TEXT"]},
    )
    ledger._conn.execute("UPDATE schema_version SET version = 1")
    try:
        assert ensure_schema(ledger._conn, migrate=True) == 1
        row = ledger._conn.execute("SELECT version FROM schema_version").fetchone()
        assert row == (2,)
        assert "migration_probe" in _campaigns_columns(ledger)
        assert ledger.get_campaign(camp_id) is not None
    finally:
        ledger._conn.execute(
            "ALTER TABLE campaigns DROP COLUMN IF EXISTS migration_probe"
        )
        _restore_stamp(ledger)


def test_migration_failure(ledger, monkeypatch: pytest.MonkeyPatch):
    """A failing migration step leaves the database at its old version."""
    monkeypatch.setattr(ledger_module, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(
        ledger_module,
        "_MIGRATIONS",
        {
            1: [
                "ALTER TABLE campaigns ADD COLUMN rollback_probe TEXT",
                "SELECT no_such_function()",
            ]
        },
    )
    ledger._conn.execute("UPDATE schema_version SET version = 1")
    try:
        with pytest.raises(psycopg.Error):
            ensure_schema(ledger._conn, migrate=True)
        row = ledger._conn.execute("SELECT version FROM schema_version").fetchone()
        assert row == (1,)
        assert "rollback_probe" not in _campaigns_columns(ledger)
    finally:
        ledger._conn.execute(
            "ALTER TABLE campaigns DROP COLUMN IF EXISTS rollback_probe"
        )
        _restore_stamp(ledger)


def test_pre_versioning_database(ledger):
    """A database from before versioning is rejected, not adopted."""
    ledger._conn.execute("DROP TABLE schema_version")
    try:
        with pytest.raises(SchemaError, match="predates schema versioning"):
            ensure_schema(ledger._conn)
    finally:
        ledger._conn.execute(_CREATE_SCHEMA_VERSION)
        ledger._conn.execute(
            "INSERT INTO schema_version (version) VALUES (%s)", (SCHEMA_VERSION,)
        )


def test_append_assigns_seq(ledger):
    """Appended events get sequential seq numbers and keep their fields."""
    event = _event()
    stored = ledger.append(event)
    assert stored.seq == 1
    assert stored.ts == event.ts
    assert stored.campaign_id == event.campaign_id


def test_tail_orders_by_seq(ledger):
    """tail returns a campaign's events in seq order."""
    camp_id = uuid.uuid4()
    first = ledger.append(_event(campaign_id=camp_id))
    second = ledger.append(_event(campaign_id=camp_id))
    events = list(ledger.tail(camp_id))
    assert [e.seq for e in events] == [first.seq, second.seq]


def test_tail_after_cursor(ledger):
    """tail with `after` skips events before the provided seq number."""
    camp_id = uuid.uuid4()
    first = ledger.append(_event(campaign_id=camp_id))
    ledger.append(_event(campaign_id=camp_id))
    assert first.seq is not None
    rest = list(ledger.tail(camp_id, after=first.seq))
    assert [e.seq for e in rest] == [2]


def test_tail_scopes_to_campaign(ledger):
    """tail returns only the requested campaign's events."""
    camp_id = uuid.uuid4()
    ledger.append(_event(campaign_id=camp_id))
    ledger.append(_event())
    assert [e.campaign_id for e in ledger.tail(camp_id)] == [camp_id]


def test_append_preserves_fields(ledger):
    """A stored event can be retrieved with reason and payload intact."""
    event = _event(reason="plan accepted", payload={"k": "v"})
    stored = ledger.append(event)
    again = next(ledger.tail(stored.campaign_id))
    assert again == stored
    assert again.reason == "plan accepted"
    assert again.payload == {"k": "v"}


def test_get_campaign(ledger):
    """get_campaign returns None for unknown IDs and the full row otherwise."""
    camp_id = uuid.uuid4()
    assert ledger.get_campaign(camp_id) is None
    plan = make_plan()
    ledger.create_campaign(
        camp_id, str(camp_id), plan, "/repo/a", 30.0, branch="main", start_sha="abc"
    )
    campaign = ledger.get_campaign(camp_id)
    assert campaign is not None
    assert campaign.campaign_id == camp_id
    assert campaign.workflow_id == str(camp_id)
    assert campaign.plan == plan
    assert campaign.repo_path == "/repo/a"
    assert campaign.branch == "main"
    assert campaign.start_sha == "abc"
    assert campaign.poll_interval_seconds == 30.0


def test_list_campaigns(ledger):
    """list_campaigns returns every campaign in creation order."""
    assert ledger.list_campaigns() == []
    camp_a = uuid.uuid4()
    camp_b = uuid.uuid4()
    ledger.create_campaign(
        camp_a, str(camp_a), make_plan(), "/repo/a", 30.0, branch="main", start_sha="a"
    )
    ledger.create_campaign(
        camp_b, str(camp_b), make_plan(), "/repo/b", 30.0, branch="main", start_sha="b"
    )
    campaigns = ledger.list_campaigns()
    assert [c.campaign_id for c in campaigns] == [camp_a, camp_b]


def test_create_campaign_idempotent(ledger):
    """Creating the same campaign twice records one campaign.created event."""
    camp_id = uuid.uuid4()
    plan = make_plan()
    assert (
        ledger.create_campaign(
            camp_id, str(camp_id), plan, "/repo/a", 30.0, branch="main", start_sha="a"
        )
        is True
    )
    assert (
        ledger.create_campaign(
            camp_id, str(camp_id), plan, "/repo/a", 30.0, branch="main", start_sha="a"
        )
        is False
    )
    events = list(ledger.tail(camp_id))
    assert len(events) == 1
    assert events[0].type == EventType.CAMPAIGN_CREATED


def test_predecessor_is_recorded(ledger):
    """Check that campaign.created records the predecessor's campaign ID and sha."""
    camp_id = uuid.uuid4()
    pred_id = uuid.uuid4()
    plan = make_plan()
    ledger.create_campaign(
        camp_id,
        str(camp_id),
        plan,
        "/repo/a",
        30.0,
        branch="main",
        start_sha="a",
        predecessor=Predecessor(campaign_id=pred_id, sha="abc123"),
    )
    events = list(ledger.tail(camp_id))
    assert len(events) == 1
    assert events[0].payload["predecessor"] == {
        "campaign_id": str(pred_id),
        "sha": "abc123",
    }
    # The payload still carries the plan itself.
    assert events[0].payload["goal"] == plan.goal


def test_campaigns_on_repo(ledger):
    """get_campaigns_on_repo returns only the campaigns on that repo."""
    repo = "/repo/a"
    assert ledger.get_campaigns_on_repo(repo) == []

    camp_id = uuid.uuid4()
    ledger.create_campaign(
        camp_id, str(camp_id), make_plan(), repo, 30.0, branch="main", start_sha="a"
    )
    # A different repo is not affected.
    assert ledger.get_campaigns_on_repo("/repo/other") == []
    campaigns = ledger.get_campaigns_on_repo(repo)
    assert [c.campaign_id for c in campaigns] == [camp_id]


def test_campaign_events(ledger):
    """get_campaign_events returns one campaign's events in seq order."""
    camp_a = uuid.uuid4()
    camp_b = uuid.uuid4()
    ledger.append(_event(campaign_id=camp_a))
    ledger.append(_event(campaign_id=camp_b))
    ledger.append(_event(campaign_id=camp_a))

    a_events = ledger.get_campaign_events(camp_a)
    assert [e.campaign_id for e in a_events] == [camp_a, camp_a]
    assert [e.seq for e in a_events] == [1, 3]
    assert len(ledger.get_campaign_events(camp_b)) == 1
    assert ledger.get_campaign_events(uuid.uuid4()) == []
