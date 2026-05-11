from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from billing_collector.application.ports.repositories import BillingCounterValue
from billing_collector.domain.models import DailyDelta
from billing_collector.infrastructure.sqlite.converters import decimal_to_text, utc_timestamp
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase

HISTORY_SOURCE = "scaleway-rest-history"


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
            connection.executemany(
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
                    kind,
                    line_fingerprint,
                    current_snapshot_id,
                    previous_snapshot_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(billing_day, billing_period, line_fingerprint, kind)
                DO UPDATE SET
                    project_name = excluded.project_name,
                    delta_euros = excluded.delta_euros,
                    delta_quantity = excluded.delta_quantity,
                    current_snapshot_id = excluded.current_snapshot_id,
                    previous_snapshot_id = excluded.previous_snapshot_id,
                    updated_at = excluded.updated_at
                """,
                [
                    (
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
                        delta.kind,
                        delta.line_fingerprint,
                        current_snapshot_id,
                        previous_snapshot_id,
                        now,
                        now,
                    )
                    for delta in deltas
                ],
            )

    def count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM daily_deltas").fetchone()[0])

    def list_billing_counters(self) -> list[BillingCounterValue]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    daily_deltas.kind,
                    daily_deltas.project_id,
                    daily_deltas.project_name,
                    daily_deltas.consumer_id,
                    daily_deltas.category_name,
                    daily_deltas.product_name,
                    daily_deltas.resource_name,
                    daily_deltas.sku,
                    daily_deltas.unit,
                    daily_deltas.currency,
                    SUM(ABS(CAST(daily_deltas.delta_euros AS REAL))) AS value,
                    SUM(CAST(daily_deltas.delta_quantity AS REAL)) AS quantity
                FROM daily_deltas
                INNER JOIN snapshots
                    ON snapshots.id = daily_deltas.current_snapshot_id
                WHERE snapshots.source != ?
                GROUP BY
                    daily_deltas.kind,
                    daily_deltas.project_id,
                    daily_deltas.project_name,
                    daily_deltas.consumer_id,
                    daily_deltas.category_name,
                    daily_deltas.product_name,
                    daily_deltas.resource_name,
                    daily_deltas.sku,
                    daily_deltas.unit,
                    daily_deltas.currency
                ORDER BY
                    daily_deltas.project_id,
                    daily_deltas.category_name,
                    daily_deltas.product_name,
                    daily_deltas.resource_name,
                    daily_deltas.sku,
                    daily_deltas.kind
                """,
                (HISTORY_SOURCE,),
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
                    value=Decimal(str(row["value"] or 0)),
                    quantity=Decimal(str(row["quantity"])) if row["quantity"] is not None else None,
                )
                for row in rows
            ]
