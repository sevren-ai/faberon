"""Append-only event ledger backed by Postgres.

Postgres is the source of truth. The ledger owns the `events` table and the
`seq` ordering key. `append` writes one event through the ledger's own
psycopg connection; `append_with_session` writes through a caller-supplied
SQLAlchemy session, used by the DBOS workflow so the insert commits with
the DBOS transaction (exactly-once under recovery). `tail` reads events in
order for the SSE stream and for replay.

The `campaigns` table records campaign-level state.
`create_campaign` inserts the campaign row and the `campaign.created` event
in one transaction so a retry never duplicates either.

The `schema_version` table stamps the schema with SCHEMA_VERSION.
`ensure_schema` creates the tables on an empty database, verifies them on
an existing one, and migrates an outdated schema step by step when asked,
keeping the data. A database with no migration path is rejected with a
SchemaError.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import LiteralString
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..schema.campaign import Campaign, Predecessor
from ..schema.events import Actor, Event, EventType
from ..schema.plan import ResearchPlan

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    seq           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL,
    campaign_id   UUID        NOT NULL,
    actor         TEXT        NOT NULL,
    type          TEXT        NOT NULL,
    reason TEXT        NOT NULL,
    payload       JSONB       NOT NULL
)
"""

_CREATE_EVENTS_INDEX = """
CREATE INDEX IF NOT EXISTS events_campaign_id_seq_idx
ON events (campaign_id, seq)
"""

_CREATE_CAMPAIGNS = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id  UUID        PRIMARY KEY,
    workflow_id   TEXT        NOT NULL,
    plan          JSONB       NOT NULL,
    repo_path     TEXT        NOT NULL,
    branch        TEXT        NOT NULL,
    start_sha     TEXT        NOT NULL,
    poll_interval_seconds DOUBLE PRECISION NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
)
"""

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version      INTEGER     NOT NULL
)
"""

# The schema this Faberon version expects. Bump on every schema change.
SCHEMA_VERSION = 1

# Ordered migration steps: _MIGRATIONS[n] upgrades a database at version n
# to n + 1. Every schema change adds one entry and bumps SCHEMA_VERSION.
# The key is the version it migrates FROM, so the first entry lands at
# key 1: {1: [...]} with SCHEMA_VERSION = 2.
_MIGRATIONS: dict[int, list[LiteralString]] = {}


class SchemaError(Exception):
    """The database schema does not match what this Faberon version expects."""


def _migrate(conn: psycopg.Connection, version: int) -> int:
    """Apply the steps from ``version`` to SCHEMA_VERSION in one transaction.

    Returns the version the database started at. Raises SchemaError before
    touching the database when a step in the chain is missing.
    """
    missing = [
        step for step in range(version, SCHEMA_VERSION) if step not in _MIGRATIONS
    ]
    if missing:
        step = missing[0]
        raise SchemaError(f"no migration from schema version {step} to {step + 1}")
    with conn.transaction():
        for step in range(version, SCHEMA_VERSION):
            for statement in _MIGRATIONS[step]:
                conn.execute(statement)
            conn.execute("UPDATE schema_version SET version = %s", (step + 1,))
    return version


def _create(conn: psycopg.Connection) -> None:
    conn.execute(_CREATE_EVENTS)
    conn.execute(_CREATE_EVENTS_INDEX)
    conn.execute(_CREATE_CAMPAIGNS)
    conn.execute(_CREATE_SCHEMA_VERSION)
    conn.execute("INSERT INTO schema_version (version) VALUES (%s)", (SCHEMA_VERSION,))


def ensure_schema(conn: psycopg.Connection, *, migrate: bool = False) -> int | None:
    """Create the schema on an empty database, verify it on an existing one.

    Returns the version the database was migrated from, or None when no
    migration ran. An outdated stamped database is migrated step by step
    when ``migrate`` is set, and rejected otherwise. A database stamped by
    a newer Faberon, and any database from before schema versioning, is
    always rejected. Raises SchemaError on any mismatch.
    """
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    }
    # Run a migration or return None if we're good
    if "schema_version" in tables:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            raise SchemaError("the schema_version table is empty")
        version = row[0]
        if version == SCHEMA_VERSION:
            return None
        if version > SCHEMA_VERSION or not migrate:
            raise SchemaError(
                f"the database is at schema version {version}, "
                f"this Faberon expects {SCHEMA_VERSION}"
            )
        return _migrate(conn, version)
    # There's an old, non-empty DB without migration options
    if "events" in tables or "campaigns" in tables:
        raise SchemaError(
            "the database is out-dated and does not have schema versioning "
            "& migration options"
        )
    # The old DB is empty: create a new one
    _create(conn)
    return None


class Ledger:
    """Append-only event ledger. Postgres is the source of truth."""

    def __init__(self, db_url: str) -> None:
        self._conn = psycopg.connect(db_url, autocommit=True)
        ensure_schema(self._conn)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def append(self, event: Event) -> Event:
        """Persist an event. Returns the event with its assigned seq."""
        row = self._conn.execute(
            """
            INSERT INTO events
                (ts, campaign_id, actor, type, reason, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING seq
            """,
            (
                event.ts,
                event.campaign_id,
                event.actor,
                event.type,
                event.reason,
                Jsonb(event.payload),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("INSERT did not return a seq")
        return event.model_copy(update={"seq": row[0]})

    def create_campaign(
        self,
        campaign_id: UUID,
        workflow_id: str,
        plan: ResearchPlan,
        repo_path: str,
        poll_interval_seconds: float,
        *,
        branch: str,
        start_sha: str,
        predecessor: Predecessor | None = None,
    ) -> bool:
        """Atomically insert a campaign row and the ``campaign.created`` event.

        Returns True if the campaign was newly created, False if it already
        existed (idempotent retry).
        """
        plan_json = plan.model_dump(mode="json")
        if predecessor is not None:
            # record both the campaign ID and the best-metric sha
            plan_json["predecessor"] = predecessor.model_dump(mode="json")
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO campaigns
                    (campaign_id, workflow_id, plan, repo_path,
                     branch, start_sha, poll_interval_seconds, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (campaign_id) DO NOTHING
                RETURNING campaign_id
                """,
                (
                    str(campaign_id),
                    workflow_id,
                    Jsonb(plan_json),
                    repo_path,
                    branch,
                    start_sha,
                    poll_interval_seconds,
                    datetime.now(UTC),
                ),
            ).fetchone()
            if row is None:
                return False
            self.append(
                Event(
                    campaign_id=campaign_id,
                    actor=Actor.HUMAN,
                    type=EventType.CAMPAIGN_CREATED,
                    reason="plan accepted",
                    payload=plan_json,
                )
            )
            return True

    def get_campaign(self, campaign_id: UUID) -> Campaign | None:
        """Return the campaign row, or None if it does not exist."""
        row = self._conn.execute(
            """
            SELECT campaign_id, workflow_id, plan, repo_path,
                   branch, start_sha, poll_interval_seconds, created_at
            FROM campaigns
            WHERE campaign_id = %s
            """,
            (str(campaign_id),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_campaign(row)

    def list_campaigns(self) -> list[Campaign]:
        """Return all campaigns, oldest first."""
        rows = self._conn.execute(
            """
            SELECT campaign_id, workflow_id, plan, repo_path,
                   branch, start_sha, poll_interval_seconds, created_at
            FROM campaigns
            ORDER BY created_at
            """
        )
        return [_row_to_campaign(row) for row in rows]

    def get_campaigns_on_repo(self, repo_path: str) -> list[Campaign]:
        """Return all campaigns targeting ``repo_path``, oldest first."""
        rows = self._conn.execute(
            """
            SELECT campaign_id, workflow_id, plan, repo_path,
                   branch, start_sha, poll_interval_seconds, created_at
            FROM campaigns
            WHERE repo_path = %s
            ORDER BY created_at
            """,
            (repo_path,),
        )
        return [_row_to_campaign(row) for row in rows]

    def append_with_session(self, session: Session, event: Event) -> int:
        """Append an event through a caller-supplied SQLAlchemy session.
        Returns the assigned seq.
        """
        row = session.execute(
            text(
                """
                INSERT INTO events
                    (ts, campaign_id, actor, type, reason, payload)
                VALUES
                    (:ts, :campaign_id, :actor, :type, :reason,
                     cast(:payload as jsonb))
                RETURNING seq
                """
            ),
            {
                "ts": event.ts,
                "campaign_id": str(event.campaign_id),
                "actor": str(event.actor),
                "type": str(event.type),
                "reason": event.reason,
                "payload": json.dumps(event.payload),
            },
        ).scalar_one()
        return int(row)

    def tail(self, campaign_id: UUID, after: int = 0) -> Iterator[Event]:
        """Yield one campaign's events with seq > after, in seq order."""
        rows = self._conn.execute(
            """
            SELECT seq, ts, campaign_id, actor, type, reason, payload
            FROM events
            WHERE campaign_id = %s AND seq > %s
            ORDER BY seq
            """,
            (str(campaign_id), after),
        )
        for row in rows:
            yield _row_to_event(row)

    def get_campaign_events(self, campaign_id: UUID) -> list[Event]:
        """Return all events for one campaign, in seq order."""
        rows = self._conn.execute(
            """
            SELECT seq, ts, campaign_id, actor, type, reason, payload
            FROM events
            WHERE campaign_id = %s
            ORDER BY seq
            """,
            (str(campaign_id),),
        )
        return [_row_to_event(row) for row in rows]


def _row_to_campaign(row: tuple) -> Campaign:
    return Campaign(
        campaign_id=row[0],
        workflow_id=row[1],
        plan=ResearchPlan.model_validate(row[2]),
        repo_path=row[3],
        branch=row[4],
        start_sha=row[5],
        poll_interval_seconds=float(row[6]),
        created_at=row[7],
    )


def _row_to_event(row: tuple) -> Event:
    return Event(
        seq=row[0],
        ts=row[1],
        campaign_id=row[2],
        actor=row[3],
        type=row[4],
        reason=row[5],
        payload=row[6],
    )
