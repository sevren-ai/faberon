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
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..schema.campaign import Campaign
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
    poll_interval_seconds DOUBLE PRECISION NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
)
"""


class Ledger:
    """Append-only event ledger. Postgres is the source of truth."""

    def __init__(self, db_url: str) -> None:
        self._conn = psycopg.connect(db_url, autocommit=True)
        self._conn.execute(_CREATE_EVENTS)
        self._conn.execute(_CREATE_EVENTS_INDEX)
        self._conn.execute(_CREATE_CAMPAIGNS)

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
    ) -> bool:
        """Atomically insert a campaign row and the ``campaign.created`` event.

        Returns True if the campaign was newly created, False if it already
        existed (idempotent retry).
        """
        plan_json = plan.model_dump(mode="json")
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO campaigns
                    (campaign_id, workflow_id, plan, repo_path,
                     poll_interval_seconds, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (campaign_id) DO NOTHING
                RETURNING campaign_id
                """,
                (
                    str(campaign_id),
                    workflow_id,
                    Jsonb(plan_json),
                    repo_path,
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
                   poll_interval_seconds, created_at
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
                   poll_interval_seconds, created_at
            FROM campaigns
            ORDER BY created_at
            """
        )
        return [_row_to_campaign(row) for row in rows]

    def campaigns_on_repo(self, repo_path: str) -> list[Campaign]:
        """Return all campaigns targeting ``repo_path``, oldest first."""
        rows = self._conn.execute(
            """
            SELECT campaign_id, workflow_id, plan, repo_path,
                   poll_interval_seconds, created_at
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

    def campaign_events(self, campaign_id: UUID) -> list[Event]:
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
        poll_interval_seconds=float(row[4]),
        created_at=row[5],
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
