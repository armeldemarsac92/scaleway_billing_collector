from __future__ import annotations

from collections.abc import Sequence

from billing_collector.domain.models import Project
from billing_collector.infrastructure.sqlite.converters import utc_timestamp
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteProjectRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(self, projects: Sequence[Project]) -> None:
        with self.database.connect() as connection:
            now = utc_timestamp()
            connection.executemany(
                """
                INSERT INTO projects (id, name, organization_id, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    organization_id = excluded.organization_id,
                    last_seen_at = excluded.last_seen_at
                """,
                [(project.id, project.name, project.organization_id, now) for project in projects],
            )

