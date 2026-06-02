from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from decimal import Decimal

from billing_collector.application.ports.repositories import BillingCounterValue
from billing_collector.domain.models import DailyDelta
from billing_collector.infrastructure.sqlite.converters import (
    decimal_from_text,
    decimal_to_text,
    utc_timestamp,
)
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase


class SqliteDailyDeltaRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(
        self,
        deltas: Sequence[DailyDelta],
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
    ) -> None:
        now = utc_timestamp()
        with self.database.connect() as connection:
            for delta in deltas:
                was_inserted = self._insert_delta(
                    connection,
                    delta,
                    current_snapshot_id=current_snapshot_id,
                    previous_snapshot_id=previous_snapshot_id,
                    now=now,
                )
                if not was_inserted:
                    self._accumulate_delta(
                        connection,
                        delta,
                        current_snapshot_id=current_snapshot_id,
                        previous_snapshot_id=previous_snapshot_id,
                        now=now,
                    )

    def _insert_delta(
        self,
        connection: sqlite3.Connection,
        delta: DailyDelta,
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
        now: str,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT INTO daily_deltas (
                billing_day,
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
                delta_euros,
                delta_quantity,
                billing_line_type,
                billing_usage_type,
                burn_rate_eligible,
                kind,
                line_fingerprint,
                current_snapshot_id,
                previous_snapshot_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(billing_day, billing_period, line_fingerprint, kind) DO NOTHING
            """,
            self._delta_params(
                delta,
                current_snapshot_id=current_snapshot_id,
                previous_snapshot_id=previous_snapshot_id,
                now=now,
            ),
        )
        return cursor.rowcount == 1

    def _accumulate_delta(
        self,
        connection: sqlite3.Connection,
        delta: DailyDelta,
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
        now: str,
    ) -> None:
        existing = connection.execute(
            """
            SELECT id, current_snapshot_id, delta_euros, delta_quantity
            FROM daily_deltas
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
        if existing is None or existing["current_snapshot_id"] == current_snapshot_id:
            return

        current_delta = decimal_from_text(existing["delta_euros"]) or Decimal("0")
        accumulated_delta = current_delta + delta.delta_value
        accumulated_quantity = self._accumulate_quantity(
            decimal_from_text(existing["delta_quantity"]),
            delta.delta_quantity,
        )

        connection.execute(
            """
            UPDATE daily_deltas
            SET
                project_name = ?,
                consumer_id = ?,
                category_name = ?,
                product_name = ?,
                resource_name = ?,
                sku = ?,
                unit = ?,
                currency = ?,
                delta_euros = ?,
                delta_quantity = ?,
                billing_line_type = ?,
                billing_usage_type = ?,
                burn_rate_eligible = ?,
                current_snapshot_id = ?,
                previous_snapshot_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                delta.project_name,
                delta.consumer_id,
                delta.category_name,
                delta.product_name,
                delta.resource_name,
                delta.sku,
                delta.unit,
                delta.currency,
                decimal_to_text(accumulated_delta),
                decimal_to_text(accumulated_quantity),
                delta.billing_line_type,
                delta.billing_usage_type,
                int(delta.burn_rate_eligible),
                current_snapshot_id,
                previous_snapshot_id,
                now,
                existing["id"],
            ),
        )

    def _delta_params(
        self,
        delta: DailyDelta,
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
        now: str,
    ) -> tuple[object, ...]:
        return (
            delta.billing_day,
            delta.billing_period,
            delta.project_id,
            delta.project_name,
            delta.consumer_id,
            delta.category_name,
            delta.product_name,
            delta.resource_name,
            delta.sku,
            delta.unit,
            delta.currency,
            decimal_to_text(delta.delta_value),
            decimal_to_text(delta.delta_quantity),
            delta.billing_line_type,
            delta.billing_usage_type,
            int(delta.burn_rate_eligible),
            delta.kind,
            delta.line_fingerprint,
            current_snapshot_id,
            previous_snapshot_id,
            now,
            now,
        )

    def _accumulate_quantity(
        self,
        current: Decimal | None,
        delta: Decimal | None,
    ) -> Decimal | None:
        if current is None or delta is None:
            return None
        return current + delta

    def count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM daily_deltas").fetchone()[0])

    def list_billing_counters(self) -> list[BillingCounterValue]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    kind,
                    project_id,
                    project_name,
                    consumer_id,
                    category_name,
                    product_name,
                    resource_name,
                    sku,
                    unit,
                    currency,
                    billing_line_type,
                    billing_usage_type,
                    burn_rate_eligible,
                    SUM(ABS(CAST(delta_euros AS REAL))) AS value,
                    SUM(CAST(delta_quantity AS REAL)) AS quantity
                FROM daily_deltas
                GROUP BY
                    kind,
                    project_id,
                    project_name,
                    consumer_id,
                    category_name,
                    product_name,
                    resource_name,
                    sku,
                    unit,
                    currency,
                    billing_line_type,
                    billing_usage_type,
                    burn_rate_eligible
                ORDER BY
                    project_id,
                    category_name,
                    product_name,
                    resource_name,
                    sku,
                    kind
                """
            ).fetchall()
            return [
                BillingCounterValue(
                    kind=row["kind"],
                    project_id=row["project_id"],
                    project_name=row["project_name"],
                    consumer_id=row["consumer_id"],
                    category_name=row["category_name"],
                    product_name=row["product_name"],
                    resource_name=row["resource_name"],
                    sku=row["sku"],
                    unit=row["unit"],
                    currency=row["currency"],
                    billing_line_type=row["billing_line_type"],
                    billing_usage_type=row["billing_usage_type"],
                    burn_rate_eligible=bool(row["burn_rate_eligible"]),
                    value=Decimal(str(row["value"] or 0)),
                    quantity=Decimal(str(row["quantity"])) if row["quantity"] is not None else None,
                )
                for row in rows
            ]
