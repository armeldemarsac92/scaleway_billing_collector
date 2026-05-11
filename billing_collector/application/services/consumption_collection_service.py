from __future__ import annotations

from billing_collector.application.ports.billing import ConsumptionReader
from billing_collector.application.ports.repositories import (
    DailyDeltaStore,
    SnapshotScope,
    SnapshotStore,
)
from billing_collector.application.services.collection_models import ConsumptionCollectionSummary
from billing_collector.domain.differ import SnapshotDiffer
from billing_collector.domain.models import BillingLine, Project, Snapshot


class ConsumptionCollectionService:
    def __init__(
        self,
        *,
        consumption_reader: ConsumptionReader,
        snapshot_store: SnapshotStore,
        daily_delta_store: DailyDeltaStore,
        differ: SnapshotDiffer | None = None,
    ) -> None:
        self.consumption_reader = consumption_reader
        self.snapshot_store = snapshot_store
        self.daily_delta_store = daily_delta_store
        self.differ = differ or SnapshotDiffer()

    def collect_period(
        self,
        *,
        billing_period: str,
        billing_day: str,
        organization_id: str,
        projects: list[Project],
        category_names: tuple[str, ...],
        source: str,
    ) -> ConsumptionCollectionSummary:
        snapshots_saved = 0
        deltas_saved = 0
        categories = category_names or (None,)

        for project in projects:
            for category_name in categories:
                snapshot = self.consumption_reader.list_consumption(
                    billing_period=billing_period,
                    project_id=project.id,
                    category_name=category_name,
                )
                snapshot = self._with_project_name(snapshot, project)
                scope = SnapshotScope(
                    billing_period=billing_period,
                    scope_type="project_category" if category_name is not None else "project",
                    organization_id=organization_id,
                    project_id=project.id,
                    category_name=category_name,
                )
                snapshot_id = self.snapshot_store.save(snapshot, scope=scope, source=source)
                snapshots_saved += 1

                previous = self.snapshot_store.previous_for_scope(
                    scope,
                    before_snapshot_id=snapshot_id,
                )
                deltas = self.differ.diff(
                    billing_day=billing_day,
                    current=snapshot,
                    previous=previous.snapshot if previous else None,
                )
                self.daily_delta_store.upsert_many(
                    deltas,
                    current_snapshot_id=snapshot_id,
                    previous_snapshot_id=previous.id if previous else None,
                )
                deltas_saved += len(deltas)

        return ConsumptionCollectionSummary(
            snapshots_saved=snapshots_saved,
            deltas_saved=deltas_saved,
        )

    def _with_project_name(self, snapshot: Snapshot, project: Project) -> Snapshot:
        return Snapshot(
            billing_period=snapshot.billing_period,
            observed_at=snapshot.observed_at,
            lines=tuple(self._line_with_project_name(line, project) for line in snapshot.lines),
        )

    def _line_with_project_name(self, line: BillingLine, project: Project) -> BillingLine:
        return BillingLine(
            billing_period=line.billing_period,
            project_id=line.project_id,
            project_name=project.name,
            consumer_id=line.consumer_id,
            category_name=line.category_name,
            product_name=line.product_name,
            resource_name=line.resource_name,
            sku=line.sku,
            unit=line.unit,
            currency=line.currency,
            value=line.value,
            billed_quantity=line.billed_quantity,
        )

