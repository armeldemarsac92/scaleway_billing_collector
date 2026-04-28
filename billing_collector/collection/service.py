from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from billing_collector.collection.differ import SnapshotDiffer
from billing_collector.collection.periods import collection_window, utc_today
from billing_collector.domain.models import BillingLine, Project, Snapshot
from billing_collector.scaleway.client import BillingClient
from billing_collector.storage.repositories import (
    DailyDeltaRepository,
    ProjectRepository,
    SnapshotRepository,
    SnapshotScope,
)


@dataclass(frozen=True, slots=True)
class CollectionSettings:
    organization_id: str
    project_ids: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()
    previous_period_backfill_days: int = 7
    source: str = "scaleway"


@dataclass(frozen=True, slots=True)
class CollectionResult:
    projects_seen: int = 0
    snapshots_saved: int = 0
    deltas_saved: int = 0


class BillingCollectionService:
    def __init__(
        self,
        *,
        client: BillingClient,
        project_repository: ProjectRepository,
        snapshot_repository: SnapshotRepository,
        delta_repository: DailyDeltaRepository,
        differ: SnapshotDiffer | None = None,
    ) -> None:
        self.client = client
        self.project_repository = project_repository
        self.snapshot_repository = snapshot_repository
        self.delta_repository = delta_repository
        self.differ = differ or SnapshotDiffer()

    def collect(
        self,
        *,
        settings: CollectionSettings,
        day: date | None = None,
    ) -> CollectionResult:
        target_day = day or utc_today()
        window = collection_window(
            day=target_day,
            previous_period_backfill_days=settings.previous_period_backfill_days,
        )
        projects = self._target_projects(settings)
        self.project_repository.upsert_many(projects)

        snapshots_saved = 0
        deltas_saved = 0
        for billing_period in window.billing_periods:
            for project in projects:
                categories = settings.category_names or (None,)
                for category_name in categories:
                    snapshot = self.client.list_consumption(
                        billing_period=billing_period,
                        project_id=project.id,
                        category_name=category_name,
                    )
                    snapshot = self._with_project_name(snapshot, project)
                    scope_type = "project_category" if category_name is not None else "project"
                    snapshot_id = self.snapshot_repository.save(
                        snapshot,
                        scope_type=scope_type,
                        organization_id=settings.organization_id,
                        project_id=project.id,
                        category_name=category_name,
                        source=settings.source,
                    )
                    snapshots_saved += 1

                    previous = self.snapshot_repository.previous_for_scope(
                        SnapshotScope(
                            billing_period=billing_period,
                            scope_type=scope_type,
                            organization_id=settings.organization_id,
                            project_id=project.id,
                            category_name=category_name,
                        ),
                        before_snapshot_id=snapshot_id,
                    )
                    deltas = self.differ.diff(
                        billing_day=window.billing_day,
                        current=snapshot,
                        previous=previous.snapshot if previous else None,
                    )
                    self.delta_repository.upsert_many(
                        deltas,
                        current_snapshot_id=snapshot_id,
                        previous_snapshot_id=previous.id if previous else None,
                    )
                    deltas_saved += len(deltas)

        return CollectionResult(
            projects_seen=len(projects),
            snapshots_saved=snapshots_saved,
            deltas_saved=deltas_saved,
        )

    def _target_projects(self, settings: CollectionSettings) -> list[Project]:
        projects = self.client.list_projects()
        if not settings.project_ids:
            return projects
        allowed = set(settings.project_ids)
        return [project for project in projects if project.id in allowed]

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

