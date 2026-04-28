from __future__ import annotations

from dataclasses import dataclass

from billing_collector.collection.service import BillingCollectionService, CollectionSettings
from billing_collector.config import Settings
from billing_collector.metrics.collector import PrometheusMetricsCollector
from billing_collector.metrics.server import MetricsServer
from billing_collector.scaleway.rest_client import ScalewayRestBillingClient
from billing_collector.storage.database import SQLiteDatabase
from billing_collector.storage.repositories import (
    DailyDeltaRepository,
    ProjectRepository,
    SnapshotRepository,
)


@dataclass(slots=True)
class Application:
    settings: Settings
    database: SQLiteDatabase
    client: ScalewayRestBillingClient
    project_repository: ProjectRepository
    snapshot_repository: SnapshotRepository
    delta_repository: DailyDeltaRepository
    collection_service: BillingCollectionService
    metrics_collector: PrometheusMetricsCollector

    @classmethod
    def from_settings(cls, settings: Settings) -> "Application":
        database = SQLiteDatabase(settings.database_path)
        database.initialize()
        client = ScalewayRestBillingClient(
            secret_key=settings.scw_secret_key,
            organization_id=settings.scw_organization_id,
            api_url=settings.scw_api_url,
        )
        project_repository = ProjectRepository(database)
        snapshot_repository = SnapshotRepository(database)
        delta_repository = DailyDeltaRepository(database)
        collection_service = BillingCollectionService(
            client=client,
            project_repository=project_repository,
            snapshot_repository=snapshot_repository,
            delta_repository=delta_repository,
        )
        metrics_collector = PrometheusMetricsCollector(delta_repository)
        return cls(
            settings=settings,
            database=database,
            client=client,
            project_repository=project_repository,
            snapshot_repository=snapshot_repository,
            delta_repository=delta_repository,
            collection_service=collection_service,
            metrics_collector=metrics_collector,
        )

    def collect_once(self) -> None:
        self.collection_service.collect(
            settings=CollectionSettings(
                organization_id=self.settings.scw_organization_id,
                project_ids=self.settings.project_ids,
                category_names=self.settings.category_names,
                previous_period_backfill_days=self.settings.previous_period_backfill_days,
                source="scaleway-rest",
            )
        )

    def serve(self) -> None:
        MetricsServer(
            host=self.settings.bind_host,
            port=self.settings.bind_port,
            collector=self.metrics_collector,
        ).serve_forever()

