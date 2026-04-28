from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from billing_collector.domain.fingerprints import line_fingerprint, tax_fingerprint
from billing_collector.domain.models import (
    BillingLine,
    DailyDelta,
    Project,
    Snapshot,
    TaxDailyDelta,
    TaxLine,
    TaxSnapshot,
)
from billing_collector.storage.database import SQLiteDatabase


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decimal_to_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal_from_text(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


@dataclass(frozen=True, slots=True)
class SnapshotScope:
    billing_period: str
    scope_type: str
    organization_id: str
    project_id: str | None = None
    category_name: str | None = None


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    id: int
    snapshot: Snapshot


@dataclass(frozen=True, slots=True)
class CounterValue:
    kind: str
    project_id: str
    project_name: str | None
    consumer_id: str
    category_name: str
    product_name: str
    resource_name: str
    sku: str
    unit: str
    currency: str
    value: Decimal
    quantity: Decimal | None


@dataclass(frozen=True, slots=True)
class TaxCounterValue:
    kind: str
    organization_id: str
    description: str
    currency: str
    rate: Decimal | None
    value: Decimal


class ProjectRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(self, projects: list[Project]) -> None:
        with self.database.connect() as connection:
            now = _now()
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


class SnapshotRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(
        self,
        snapshot: Snapshot,
        *,
        scope_type: str,
        organization_id: str,
        project_id: str | None = None,
        category_name: str | None = None,
        source: str = "test",
        raw: object | None = None,
    ) -> int:
        created_at = _now()
        raw_json = json.dumps(raw if raw is not None else [], sort_keys=True)
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
                    scope_type,
                    organization_id,
                    project_id,
                    category_name,
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
            _decimal_to_text(line.value),
            _decimal_to_text(line.billed_quantity),
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
        value = _decimal_from_text(row["value_euros"])
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
            billed_quantity=_decimal_from_text(row["billed_quantity"]),
        )


class DailyDeltaRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(
        self,
        deltas: list[DailyDelta],
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
    ) -> None:
        now = _now()
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
                        _decimal_to_text(delta.delta_value),
                        _decimal_to_text(delta.delta_quantity),
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

    def counter_values(self) -> list[CounterValue]:
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
                    currency
                ORDER BY project_id, category_name, product_name, resource_name, sku, kind
                """
            ).fetchall()
            return [
                CounterValue(
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


@dataclass(frozen=True, slots=True)
class StoredTaxSnapshot:
    id: int
    snapshot: TaxSnapshot


class TaxSnapshotRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, snapshot: TaxSnapshot, *, raw: object | None = None) -> int:
        created_at = _now()
        raw_json = json.dumps(raw if raw is not None else [], sort_keys=True)
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tax_snapshots (
                    billing_period,
                    observed_at,
                    organization_id,
                    raw_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.billing_period,
                    snapshot.observed_at.isoformat(),
                    snapshot.organization_id,
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
                        _decimal_to_text(line.rate),
                        _decimal_to_text(line.total_tax_value),
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
        value = _decimal_from_text(row["total_tax_value"])
        if value is None:
            raise ValueError("tax line value cannot be null")
        return TaxLine(
            billing_period=row["billing_period"],
            organization_id=row["organization_id"],
            description=row["description"],
            currency=row["currency"],
            rate=_decimal_from_text(row["rate"]),
            total_tax_value=value,
        )


class TaxDeltaRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert_many(
        self,
        deltas: list[TaxDailyDelta],
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
    ) -> None:
        now = _now()
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
                        _decimal_to_text(delta.rate),
                        _decimal_to_text(delta.delta_value),
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

    def counter_values(self) -> list[TaxCounterValue]:
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
                GROUP BY kind, organization_id, description, currency, rate
                ORDER BY organization_id, description, kind
                """
            ).fetchall()
            return [
                TaxCounterValue(
                    kind=row["kind"],
                    organization_id=row["organization_id"],
                    description=row["description"],
                    currency=row["currency"],
                    rate=_decimal_from_text(row["rate"]),
                    value=Decimal(str(row["value"] or 0)),
                )
                for row in rows
            ]
