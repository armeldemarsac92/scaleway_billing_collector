from __future__ import annotations

from dataclasses import dataclass

from billing_collector.application.services.billing_collection_service import BillingCollectionService
from billing_collector.application.services.collection_models import CollectionResult, CollectionSettings
from billing_collector.application.services.collection_models import HistorySeedResult, HistorySeedSettings
from billing_collector.application.services.consumption_collection_service import (
    ConsumptionCollectionService,
)
from billing_collector.application.services.history_seed_service import HistorySeedService
from billing_collector.application.services.tax_collection_service import TaxCollectionService
from billing_collector.config import Settings
from billing_collector.infrastructure.metrics.prometheus_metrics_renderer import (
    PrometheusMetricsRenderer,
)
from billing_collector.infrastructure.scaleway.rest_billing_client import ScalewayRestBillingClient
from billing_collector.infrastructure.scheduling.interval_scheduler import IntervalScheduler
from billing_collector.infrastructure.sqlite.collector_state_repository import (
    SqliteCollectorStateRepository,
)
from billing_collector.infrastructure.sqlite.daily_delta_repository import SqliteDailyDeltaRepository
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase
from billing_collector.infrastructure.sqlite.project_repository import SqliteProjectRepository
from billing_collector.infrastructure.sqlite.snapshot_repository import SqliteSnapshotRepository
from billing_collector.infrastructure.sqlite.tax_delta_repository import SqliteTaxDeltaRepository
from billing_collector.infrastructure.sqlite.tax_snapshot_repository import SqliteTaxSnapshotRepository
from billing_collector.infrastructure.web.metrics_server import MetricsServer


@dataclass(slots=True)
class Application:
    settings: Settings
    database: SQLiteDatabase
    billing_client: ScalewayRestBillingClient
    project_repository: SqliteProjectRepository
    snapshot_repository: SqliteSnapshotRepository
    daily_delta_repository: SqliteDailyDeltaRepository
    tax_snapshot_repository: SqliteTaxSnapshotRepository
    tax_delta_repository: SqliteTaxDeltaRepository
    collector_state_repository: SqliteCollectorStateRepository
    collection_service: BillingCollectionService
    history_seed_service: HistorySeedService
    metrics_renderer: PrometheusMetricsRenderer

    @classmethod
    def from_settings(cls, settings: Settings) -> "Application":
        database = SQLiteDatabase(settings.database_path)
        database.initialize()
        billing_client = ScalewayRestBillingClient(
            secret_key=settings.scw_secret_key,
            organization_id=settings.scw_organization_id,
            api_url=settings.scw_api_url,
        )
        project_repository = SqliteProjectRepository(database)
        snapshot_repository = SqliteSnapshotRepository(database)
        daily_delta_repository = SqliteDailyDeltaRepository(database)
        tax_snapshot_repository = SqliteTaxSnapshotRepository(database)
        tax_delta_repository = SqliteTaxDeltaRepository(database)
        collector_state_repository = SqliteCollectorStateRepository(database)
        consumption_collection_service = ConsumptionCollectionService(
            consumption_reader=billing_client,
            snapshot_store=snapshot_repository,
            daily_delta_store=daily_delta_repository,
        )
        tax_collection_service = TaxCollectionService(
            tax_reader=billing_client,
            tax_snapshot_store=tax_snapshot_repository,
            tax_delta_store=tax_delta_repository,
        )
        collection_service = BillingCollectionService(
            project_reader=billing_client,
            project_writer=project_repository,
            consumption_collection_service=consumption_collection_service,
            tax_collection_service=tax_collection_service,
        )
        history_seed_service = HistorySeedService(
            project_reader=billing_client,
            project_writer=project_repository,
            consumption_reader=billing_client,
            tax_reader=billing_client,
            snapshot_store=snapshot_repository,
            daily_delta_store=daily_delta_repository,
            tax_snapshot_store=tax_snapshot_repository,
            tax_delta_store=tax_delta_repository,
            state_store=collector_state_repository,
        )
        metrics_renderer = PrometheusMetricsRenderer(
            billing_counter_reader=daily_delta_repository,
            tax_counter_reader=tax_delta_repository,
        )
        return cls(
            settings=settings,
            database=database,
            billing_client=billing_client,
            project_repository=project_repository,
            snapshot_repository=snapshot_repository,
            daily_delta_repository=daily_delta_repository,
            tax_snapshot_repository=tax_snapshot_repository,
            tax_delta_repository=tax_delta_repository,
            collector_state_repository=collector_state_repository,
            collection_service=collection_service,
            history_seed_service=history_seed_service,
            metrics_renderer=metrics_renderer,
        )

    def collect_once(self) -> CollectionResult:
        return self.collection_service.collect(
            settings=CollectionSettings(
                organization_id=self.settings.scw_organization_id,
                project_ids=self.settings.project_ids,
                category_names=self.settings.category_names,
                previous_period_backfill_days=self.settings.previous_period_backfill_days,
                source="scaleway-rest",
            )
        )

    def seed_history(
        self,
        *,
        start_period: str | None = None,
        end_period: str | None = None,
        empty_stop_months: int | None = None,
        force: bool = False,
    ) -> HistorySeedResult:
        return self.history_seed_service.seed(
            settings=HistorySeedSettings(
                organization_id=self.settings.scw_organization_id,
                project_ids=self.settings.project_ids,
                category_names=self.settings.category_names,
                start_period=start_period or self.settings.history_start_period,
                end_period=end_period or self.settings.history_end_period,
                empty_stop_months=empty_stop_months
                if empty_stop_months is not None
                else self.settings.history_empty_stop_months,
                source="scaleway-rest-history",
                force=force,
            )
        )

    def serve(self) -> None:
        scheduler = IntervalScheduler(
            job=self.collect_once,
            interval_seconds=self.settings.collection_interval_seconds,
            run_on_start=self.settings.collect_on_start,
        )
        scheduler.start()
        MetricsServer(
            host=self.settings.bind_host,
            port=self.settings.bind_port,
            metrics_renderer=self.metrics_renderer,
        ).serve_forever()
