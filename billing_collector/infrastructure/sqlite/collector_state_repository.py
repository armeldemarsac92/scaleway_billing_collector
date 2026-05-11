from __future__ import annotations

from billing_collector.infrastructure.sqlite.converters import utc_timestamp
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteCollectorStateRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, key: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM collector_state WHERE key = ?",
                (key,),
            ).fetchone()
            return None if row is None else str(row["value"])

    def set(self, key: str, value: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO collector_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, utc_timestamp()),
            )
