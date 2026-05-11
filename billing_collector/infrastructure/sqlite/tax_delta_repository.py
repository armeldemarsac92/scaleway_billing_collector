from __future__ import annotations

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

HISTORY_SOURCE = "scaleway-rest-history"


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
            connection.executemany(
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
                ON CONFLICT(billing_day, billing_period, line_fingerprint, kind)
                DO UPDATE SET
                    delta_euros = excluded.delta_euros,
                    current_tax_snapshot_id = excluded.current_tax_snapshot_id,
                    previous_tax_snapshot_id = excluded.previous_tax_snapshot_id,
                    updated_at = excluded.updated_at
                """,
                [
                    (
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
                    for delta in deltas
                ],
            )

    def list_tax_counters(self) -> list[TaxCounterValue]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    tax_daily_deltas.kind,
                    tax_daily_deltas.organization_id,
                    tax_daily_deltas.description,
                    tax_daily_deltas.currency,
                    tax_daily_deltas.rate,
                    SUM(ABS(CAST(tax_daily_deltas.delta_euros AS REAL))) AS value
                FROM tax_daily_deltas
                INNER JOIN tax_snapshots
                    ON tax_snapshots.id = tax_daily_deltas.current_tax_snapshot_id
                WHERE tax_snapshots.source != ?
                GROUP BY
                    tax_daily_deltas.kind,
                    tax_daily_deltas.organization_id,
                    tax_daily_deltas.description,
                    tax_daily_deltas.currency,
                    tax_daily_deltas.rate
                ORDER BY
                    tax_daily_deltas.organization_id,
                    tax_daily_deltas.description,
                    tax_daily_deltas.kind
                """,
                (HISTORY_SOURCE,),
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
