from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from billing_collector.application.ports.repositories import StoredTaxSnapshot
from billing_collector.domain.fingerprints import tax_fingerprint
from billing_collector.domain.models import TaxLine, TaxSnapshot
from billing_collector.infrastructure.sqlite.converters import (
    decimal_from_text,
    decimal_to_text,
    utc_timestamp,
)
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteTaxSnapshotRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, snapshot: TaxSnapshot, *, source: str) -> int:
        created_at = utc_timestamp()
        raw_json = json.dumps([], sort_keys=True)
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tax_snapshots (
                    billing_period,
                    observed_at,
                    organization_id,
                    source,
                    raw_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.billing_period,
                    snapshot.observed_at.isoformat(),
                    snapshot.organization_id,
                    source,
                    raw_json,
                    created_at,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO tax_snapshot_lines (
                    tax_snapshot_id,
                    billing_period,
                    organization_id,
                    description,
                    currency,
                    rate,
                    total_tax_value,
                    line_fingerprint,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        line.billing_period,
                        line.organization_id,
                        line.description,
                        line.currency,
                        decimal_to_text(line.rate),
                        decimal_to_text(line.total_tax_value),
                        tax_fingerprint(line),
                        "{}",
                    )
                    for line in snapshot.lines
                ],
            )
            return snapshot_id

    def previous(
        self,
        *,
        billing_period: str,
        organization_id: str,
        before_snapshot_id: int,
    ) -> StoredTaxSnapshot | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, billing_period, observed_at, organization_id
                FROM tax_snapshots
                WHERE billing_period = ?
                  AND organization_id = ?
                  AND id < ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (billing_period, organization_id, before_snapshot_id),
            ).fetchone()
            if row is None:
                return None
            return StoredTaxSnapshot(id=int(row["id"]), snapshot=self._load(connection, row))

    def _load(self, connection: sqlite3.Connection, row: sqlite3.Row) -> TaxSnapshot:
        line_rows = connection.execute(
            """
            SELECT *
            FROM tax_snapshot_lines
            WHERE tax_snapshot_id = ?
            ORDER BY id ASC
            """,
            (row["id"],),
        ).fetchall()
        return TaxSnapshot(
            billing_period=row["billing_period"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            organization_id=row["organization_id"],
            lines=tuple(self._line_from_row(line_row) for line_row in line_rows),
        )

    def _line_from_row(self, row: sqlite3.Row) -> TaxLine:
        value = decimal_from_text(row["total_tax_value"])
        if value is None:
            raise ValueError("tax line value cannot be null")
        return TaxLine(
            billing_period=row["billing_period"],
            organization_id=row["organization_id"],
            description=row["description"],
            currency=row["currency"],
            rate=decimal_from_text(row["rate"]),
            total_tax_value=value,
        )
