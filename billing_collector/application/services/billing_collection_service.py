from __future__ import annotations

from datetime import date

from billing_collector.application.periods import collection_window, utc_today
from billing_collector.application.ports.billing import ProjectReader
from billing_collector.application.ports.repositories import ProjectWriter
from billing_collector.application.services.collection_models import (
    CollectionResult,
    CollectionSettings,
)
from billing_collector.application.services.consumption_collection_service import (
    ConsumptionCollectionService,
)
from billing_collector.application.services.tax_collection_service import TaxCollectionService
from billing_collector.domain.models import Project


class BillingCollectionService:
    def __init__(
        self,
        *,
        project_reader: ProjectReader,
        project_writer: ProjectWriter,
        consumption_collection_service: ConsumptionCollectionService,
        tax_collection_service: TaxCollectionService,
    ) -> None:
        self.project_reader = project_reader
        self.project_writer = project_writer
        self.consumption_collection_service = consumption_collection_service
        self.tax_collection_service = tax_collection_service

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
        self.project_writer.upsert_many(projects)

        snapshots_saved = 0
        deltas_saved = 0
        tax_snapshots_saved = 0
        tax_deltas_saved = 0

        for billing_period in window.billing_periods:
            consumption_summary = self.consumption_collection_service.collect_period(
                billing_period=billing_period,
                billing_day=window.billing_day,
                organization_id=settings.organization_id,
                projects=projects,
                category_names=settings.category_names,
                source=settings.source,
            )
            tax_summary = self.tax_collection_service.collect_period(
                billing_period=billing_period,
                billing_day=window.billing_day,
                organization_id=settings.organization_id,
                source=settings.source,
            )
            snapshots_saved += consumption_summary.snapshots_saved
            deltas_saved += consumption_summary.deltas_saved
            tax_snapshots_saved += tax_summary.snapshots_saved
            tax_deltas_saved += tax_summary.deltas_saved

        return CollectionResult(
            projects_seen=len(projects),
            snapshots_saved=snapshots_saved,
            deltas_saved=deltas_saved,
            tax_snapshots_saved=tax_snapshots_saved,
            tax_deltas_saved=tax_deltas_saved,
        )

    def _target_projects(self, settings: CollectionSettings) -> list[Project]:
        projects = self.project_reader.list_projects()
        if not settings.project_ids:
            return projects
        allowed_project_ids = set(settings.project_ids)
        return [project for project in projects if project.id in allowed_project_ids]
