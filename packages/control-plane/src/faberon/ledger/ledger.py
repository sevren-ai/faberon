"""Append-only event ledger backed by Postgres.

Postgres is the source of truth. The ledger owns the `events` table and the
`seq` ordering key. `append` writes one event; `tail` reads events in order
for the SSE stream and for replay.
"""

from collections.abc import Iterator

import psycopg
from psycopg.types.json import Jsonb

from ..schema.events import Event

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    seq           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL,
    campaign_id   UUID        NOT NULL,
    actor         TEXT        NOT NULL,
    type          TEXT        NOT NULL,
    justification TEXT        NOT NULL,
    payload       JSONB       NOT NULL
)
"""


class Ledger:
    """Append-only event ledger. Postgres is the source of truth."""

    def __init__(self, db_url: str) -> None:
        self._conn = psycopg.connect(db_url, autocommit=True)
        self._conn.execute(_CREATE_TABLE)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def append(self, event: Event) -> Event:
        """Persist an event. Returns the event with its assigned seq."""
        row = self._conn.execute(
            """
            INSERT INTO events
                (ts, campaign_id, actor, type, justification, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING seq
            """,
            (
                event.ts,
                event.campaign_id,
                event.actor,
                event.type,
                event.justification,
                Jsonb(event.payload),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("INSERT did not return a seq")
        return event.model_copy(update={"seq": row[0]})

    def tail(self, after: int = 0) -> Iterator[Event]:
        """Yield events with seq > after, in order. after=0 starts from the first."""
        rows = self._conn.execute(
            """
            SELECT seq, ts, campaign_id, actor, type, justification, payload
            FROM events
            WHERE seq > %s
            ORDER BY seq
            """,
            (after,),
        )
        for row in rows:
            yield _row_to_event(row)


def _row_to_event(row: tuple) -> Event:
    return Event(
        seq=row[0],
        ts=row[1],
        campaign_id=row[2],
        actor=row[3],
        type=row[4],
        justification=row[5],
        payload=row[6],
    )
