from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from billing_collector.application.ports.repositories import SnapshotScope, StoredSnapshot
from billing_collector.domain.fingerprints import line_fingerprint
from billing_collector.domain.models import BillingLine, Snapshot
from billing_collector.infrastructure.sqlite.converters import (
    decimal_from_text,
    decimal_to_text,
    utc_timestamp,
)
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteSnapshotRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, snapshot: Snapshot, *, scope: SnapshotScope, source: str) -> int:
        created_at = utc_timestamp()
        raw_json = json.dumps([], sort_keys=True)
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO snapshots (
                    billing_period,
                    observed_at,
                    scope_type,
                    organization_id,
                    project_id,
                    category_name,
                    source,
                    raw_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.billing_period,
                    snapshot.observed_at.isoformat(),
                    scope.scope_type,
                    scope.organization_id,
                    scope.project_id,
                    scope.category_name,
                    source,
                    raw_json,
                    created_at,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO snapshot_lines (
                    snapshot_id,
                    billing_period,
                    project_id,
                    project_name,
                    consumer_id,
                    category_name,
                    product_name,
                    resource_name,
                    sku,
                    unit,
                    currency,
                    value_euros,
                    billed_quantity,
                    line_fingerprint,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._line_params(snapshot_id, line) for line in snapshot.lines],
            )
            return snapshot_id

    def previous_for_scope(
        self,
        scope: SnapshotScope,
        *,
        before_snapshot_id: int,
    ) -> StoredSnapshot | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, billing_period, observed_at
                FROM snapshots
                WHERE billing_period = ?
                  AND scope_type = ?
                  AND organization_id = ?
                  AND COALESCE(project_id, '') = COALESCE(?, '')
                  AND COALESCE(category_name, '') = COALESCE(?, '')
                  AND id < ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    scope.billing_period,
                    scope.scope_type,
                    scope.organization_id,
                    scope.project_id,
                    scope.category_name,
                    before_snapshot_id,
                ),
            ).fetchone()
            if row is None:
                return None
            return StoredSnapshot(
                id=int(row["id"]),
                snapshot=self._load_snapshot(connection, row),
            )

    def get(self, snapshot_id: int) -> StoredSnapshot:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, billing_period, observed_at
                FROM snapshots
                WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"snapshot {snapshot_id} not found")
            return StoredSnapshot(id=snapshot_id, snapshot=self._load_snapshot(connection, row))

    def _line_params(self, snapshot_id: int, line: BillingLine) -> tuple[object, ...]:
        return (
            snapshot_id,
            line.billing_period,
            line.project_id,
            line.project_name,
            line.consumer_id,
            line.category_name,
            line.product_name,
            line.resource_name,
            line.sku,
            line.unit,
            line.currency,
            decimal_to_text(line.value),
            decimal_to_text(line.billed_quantity),
            line_fingerprint(line),
            "{}",
        )

    def _load_snapshot(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Snapshot:
        line_rows = connection.execute(
            """
            SELECT *
            FROM snapshot_lines
            WHERE snapshot_id = ?
            ORDER BY id ASC
            """,
            (row["id"],),
        ).fetchall()
        return Snapshot(
            billing_period=row["billing_period"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            lines=tuple(self._line_from_row(line_row) for line_row in line_rows),
        )

    def _line_from_row(self, row: sqlite3.Row) -> BillingLine:
        value = decimal_from_text(row["value_euros"])
        if value is None:
            raise ValueError("snapshot line value cannot be null")
        return BillingLine(
            billing_period=row["billing_period"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            consumer_id=row["consumer_id"],
            category_name=row["category_name"],
            product_name=row["product_name"],
            resource_name=row["resource_name"],
            sku=row["sku"],
            unit=row["unit"],
            currency=row["currency"],
            value=value,
            billed_quantity=decimal_from_text(row["billed_quantity"]),
        )
