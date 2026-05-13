from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from billing_collector.domain.models import DailyDelta, Project, Snapshot, TaxDailyDelta, TaxSnapshot


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
class StoredTaxSnapshot:
    id: int
    snapshot: TaxSnapshot


@dataclass(frozen=True, slots=True)
class BillingCounterValue:
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
    billing_line_type: str
    billing_usage_type: str
    burn_rate_eligible: bool
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


class ProjectWriter(Protocol):
    def upsert_many(self, projects: Sequence[Project]) -> None:
        ...


class SnapshotStore(Protocol):
    def save(self, snapshot: Snapshot, *, scope: SnapshotScope, source: str) -> int:
        ...

    def previous_for_scope(
        self,
        scope: SnapshotScope,
        *,
        before_snapshot_id: int,
    ) -> StoredSnapshot | None:
        ...


class DailyDeltaStore(Protocol):
    def upsert_many(
        self,
        deltas: Sequence[DailyDelta],
        *,
        current_snapshot_id: int,
        previous_snapshot_id: int | None,
    ) -> None:
        ...


class TaxSnapshotStore(Protocol):
    def save(self, snapshot: TaxSnapshot, *, source: str) -> int:
        ...

    def previous(
        self,
        *,
        billing_period: str,
        organization_id: str,
        before_snapshot_id: int,
    ) -> StoredTaxSnapshot | None:
        ...


class TaxDeltaStore(Protocol):
    def upsert_many(
        self,
        deltas: Sequence[TaxDailyDelta],
        *,
        current_tax_snapshot_id: int,
        previous_tax_snapshot_id: int | None,
    ) -> None:
        ...


class BillingCounterReader(Protocol):
    def list_billing_counters(self) -> list[BillingCounterValue]:
        ...


class TaxCounterReader(Protocol):
    def list_tax_counters(self) -> list[TaxCounterValue]:
        ...
