from __future__ import annotations

from billing_collector.application.ports.billing import TaxReader
from billing_collector.application.ports.repositories import TaxDeltaStore, TaxSnapshotStore
from billing_collector.application.services.collection_models import TaxCollectionSummary
from billing_collector.domain.differ import TaxSnapshotDiffer


class TaxCollectionService:
    def __init__(
        self,
        *,
        tax_reader: TaxReader,
        tax_snapshot_store: TaxSnapshotStore,
        tax_delta_store: TaxDeltaStore,
        differ: TaxSnapshotDiffer | None = None,
    ) -> None:
        self.tax_reader = tax_reader
        self.tax_snapshot_store = tax_snapshot_store
        self.tax_delta_store = tax_delta_store
        self.differ = differ or TaxSnapshotDiffer()

    def collect_period(
        self,
        *,
        billing_period: str,
        billing_day: str,
        organization_id: str,
        source: str,
    ) -> TaxCollectionSummary:
        snapshot = self.tax_reader.list_taxes(
            billing_period=billing_period,
            organization_id=organization_id,
        )
        snapshot_id = self.tax_snapshot_store.save(snapshot, source=source)
        previous = self.tax_snapshot_store.previous(
            billing_period=billing_period,
            organization_id=organization_id,
            before_snapshot_id=snapshot_id,
        )
        deltas = self.differ.diff(
            billing_day=billing_day,
            current=snapshot,
            previous=previous.snapshot if previous else None,
        )
        self.tax_delta_store.upsert_many(
            deltas,
            current_tax_snapshot_id=snapshot_id,
            previous_tax_snapshot_id=previous.id if previous else None,
        )
        return TaxCollectionSummary(snapshots_saved=1, deltas_saved=len(deltas))
