"""SQL-based CDC stream reader for PostgreSQL.

Uses pg_logical_slot_peek_binary_changes() to read WAL changes via a regular
SQL connection (not the streaming replication protocol). This is the Option E
approach — batch reads on a schedule.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
from psycopg import sql

from posthog.temporal.data_imports.cdc.types import ChangeEvent
from posthog.temporal.data_imports.sources.postgres.cdc.decoder import PgOutputDecoder
from posthog.temporal.data_imports.sources.postgres.postgres import _connect_to_postgres, get_primary_key_columns

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PgCDCConnectionParams:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"
    slot_name: str = ""
    publication_name: str = ""


class PgCDCStreamReader:
    """Reads WAL changes from a PostgreSQL replication slot using SQL queries.

    Uses pg_logical_slot_peek_binary_changes() for non-destructive reads
    and pg_replication_slot_advance() for explicit position confirmation.
    """

    def __init__(self, params: PgCDCConnectionParams) -> None:
        self._params = params
        self._conn: psycopg.Connection | None = None
        self._decoder = PgOutputDecoder()

    def connect(self) -> None:
        self._conn = _connect_to_postgres(
            host=self._params.host,
            port=self._params.port,
            database=self._params.database,
            user=self._params.user,
            password=self._params.password,
        )

    def read_changes(self, from_position: str | None = None) -> Iterator[ChangeEvent]:
        """Read all pending WAL changes from the replication slot.

        Uses peek (non-consuming) so the slot position is not advanced.
        Call confirm_position() after successful processing.
        """
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")

        query = sql.SQL(
            "SELECT lsn, xid, data FROM pg_logical_slot_peek_binary_changes("
            "{slot_name}, NULL, NULL, "
            "'proto_version', '1', "
            "'publication_names', {pub_name}"
            ")"
        ).format(
            slot_name=sql.Literal(self._params.slot_name),
            pub_name=sql.Literal(self._params.publication_name),
        )

        with self._conn.cursor() as cur:
            cur.execute(query)

            for row in cur:
                lsn_str: str = row[0]
                # xid: int = row[1]  # not needed
                data: bytes = row[2]

                events = self._decoder.decode_message(data, lsn_str)
                yield from events

    def confirm_position(self, position: str) -> None:
        """Advance the replication slot to the given LSN.

        This consumes all WAL up to and including the given position.
        Only call after successful processing of all events.
        """
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")

        query = sql.SQL("SELECT pg_replication_slot_advance({slot_name}, {lsn})").format(
            slot_name=sql.Literal(self._params.slot_name),
            lsn=sql.Literal(position),
        )

        with self._conn.cursor() as cur:
            cur.execute(query)
        self._conn.commit()

        logger.info("Advanced slot %s to position %s", self._params.slot_name, position)

    def get_primary_key_columns(self, schema_name: str, table_names: list[str]) -> dict[str, list[str]]:
        """Query information_schema for PK columns of the given tables.

        Returns a dict of table_name → list of PK column names.
        """
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return get_primary_key_columns(self._conn, schema_name, table_names)

    @property
    def truncated_tables(self) -> list[str]:
        """Tables that received a TRUNCATE during the last read_changes() call."""
        return self._decoder.truncated_tables

    def clear_truncated_tables(self) -> None:
        self._decoder.clear_truncated_tables()

    def get_decoder_key_columns(self, table_name: str) -> list[str]:
        """Return PK columns discovered by the decoder from Relation messages during read_changes()."""
        return self._decoder.get_key_columns(table_name)

    @property
    def last_commit_end_lsn(self) -> str | None:
        """End LSN of the most recently committed transaction.

        Non-None even when only TRUNCATE messages were decoded (no ChangeEvents).
        Use this to advance the slot when event_count == 0 but truncates occurred.
        """
        return self._decoder.last_commit_end_lsn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
