from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from decimal import Decimal

from billing_collector.application.ports.repositories import TaxCounterValue
from billing_collector.domain.models import TaxDailyDelta
from billing_collector.infrastructure.sqlite.converters import (
    decimal_from_text,
    decimal_to_text,
    utc_timestamp,
)
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteTaxDeltaRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(
        self,
        deltas: Sequence[TaxDailyDelta],
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
    ) -> None:
        now = utc_timestamp()
        with self.database.connect() as connection:
            for delta in deltas:
                was_inserted = self._insert_delta(
                    connection,
                    delta,
                    current_tax_snapshot_id=current_tax_snapshot_id,
                    previous_tax_snapshot_id=previous_tax_snapshot_id,
                    now=now,
                )
                if not was_inserted:
                    self._accumulate_delta(
                        connection,
                        delta,
                        current_tax_snapshot_id=current_tax_snapshot_id,
                        previous_tax_snapshot_id=previous_tax_snapshot_id,
                        now=now,
                    )

    def _insert_delta(
        self,
        connection: sqlite3.Connection,
        delta: TaxDailyDelta,
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
        now: str,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT INTO tax_daily_deltas (
                billing_day,
                billing_period,
                organization_id,
                description,
                currency,
                rate,
                delta_euros,
                kind,
                line_fingerprint,
                current_tax_snapshot_id,
                previous_tax_snapshot_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(billing_day, billing_period, line_fingerprint, kind) DO NOTHING
            """,
            self._delta_params(
                delta,
                current_tax_snapshot_id=current_tax_snapshot_id,
                previous_tax_snapshot_id=previous_tax_snapshot_id,
                now=now,
            ),
        )
        return cursor.rowcount == 1

    def _accumulate_delta(
        self,
        connection: sqlite3.Connection,
        delta: TaxDailyDelta,
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
        now: str,
    ) -> None:
        existing = connection.execute(
            """
            SELECT id, current_tax_snapshot_id, delta_euros
            FROM tax_daily_deltas
            WHERE billing_day = ?
              AND billing_period = ?
              AND line_fingerprint = ?
              AND kind = ?
            """,
            (
                delta.billing_day,
                delta.billing_period,
                delta.line_fingerprint,
                delta.kind,
            ),
        ).fetchone()
        if existing is None or existing["current_tax_snapshot_id"] == current_tax_snapshot_id:
            return

        current_delta = decimal_from_text(existing["delta_euros"]) or Decimal("0")
        accumulated_delta = current_delta + delta.delta_value

        connection.execute(
            """
            UPDATE tax_daily_deltas
            SET
                organization_id = ?,
                description = ?,
                currency = ?,
                rate = ?,
                delta_euros = ?,
                current_tax_snapshot_id = ?,
                previous_tax_snapshot_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                delta.organization_id,
                delta.description,
                delta.currency,
                decimal_to_text(delta.rate),
                decimal_to_text(accumulated_delta),
                current_tax_snapshot_id,
                previous_tax_snapshot_id,
                now,
                existing["id"],
            ),
        )

    def _delta_params(
        self,
        delta: TaxDailyDelta,
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
        now: str,
    ) -> tuple[object, ...]:
        return (
            delta.billing_day,
            delta.billing_period,
            delta.organization_id,
            delta.description,
            delta.currency,
            decimal_to_text(delta.rate),
            decimal_to_text(delta.delta_value),
            delta.kind,
            delta.line_fingerprint,
            current_tax_snapshot_id,
            previous_tax_snapshot_id,
            now,
            now,
        )

    def list_tax_counters(self) -> list[TaxCounterValue]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    kind,
                    organization_id,
                    description,
                    currency,
                    rate,
                    SUM(ABS(CAST(delta_euros AS REAL))) AS value
                FROM tax_daily_deltas
                GROUP BY
                    kind,
                    organization_id,
                    description,
                    currency,
                    rate
                ORDER BY
                    organization_id,
                    description,
                    kind
                """
            ).fetchall()
            return [
                TaxCounterValue(
                    kind=row["kind"],
                    organization_id=row["organization_id"],
                    description=row["description"],
                    currency=row["currency"],
                    rate=decimal_from_text(row["rate"]),
                    value=Decimal(str(row["value"] or 0)),
                )
                for row in rows
            ]
