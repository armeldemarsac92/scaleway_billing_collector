from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from billing_collector.application.periods import (
    billing_period_last_day,
    previous_billing_period,
    previous_closed_billing_period,
    utc_today,
)
from billing_collector.application.ports.billing import ConsumptionReader, ProjectReader, TaxReader
from billing_collector.application.ports.repositories import (
    CollectorStateStore,
    DailyDeltaStore,
    ProjectWriter,
    SnapshotScope,
    SnapshotStore,
    TaxDeltaStore,
    TaxSnapshotStore,
)
from billing_collector.application.services.collection_models import (
    HistorySeedResult,
    HistorySeedSettings,
)
from billing_collector.domain.differ import SnapshotDiffer, TaxSnapshotDiffer
from billing_collector.domain.models import BillingLine, Project, Snapshot, TaxSnapshot


HISTORY_SEED_STATE_KEY = "history_seed.completed"


@dataclass(frozen=True, slots=True)
class PeriodSeedSummary:
    snapshots_saved: int = 0
    deltas_saved: int = 0
    tax_snapshots_saved: int = 0
    tax_deltas_saved: int = 0

    @property
    def has_data(self) -> bool:
        return self.snapshots_saved > 0 or self.tax_snapshots_saved > 0


class HistorySeedService:
    def __init__(
        self,
        *,
        project_reader: ProjectReader,
        project_writer: ProjectWriter,
        consumption_reader: ConsumptionReader,
        tax_reader: TaxReader,
        snapshot_store: SnapshotStore,
        daily_delta_store: DailyDeltaStore,
        tax_snapshot_store: TaxSnapshotStore,
        tax_delta_store: TaxDeltaStore,
        state_store: CollectorStateStore,
        differ: SnapshotDiffer | None = None,
        tax_differ: TaxSnapshotDiffer | None = None,
    ) -> None:
        self.project_reader = project_reader
        self.project_writer = project_writer
        self.consumption_reader = consumption_reader
        self.tax_reader = tax_reader
        self.snapshot_store = snapshot_store
        self.daily_delta_store = daily_delta_store
        self.tax_snapshot_store = tax_snapshot_store
        self.tax_delta_store = tax_delta_store
        self.state_store = state_store
        self.differ = differ or SnapshotDiffer()
        self.tax_differ = tax_differ or TaxSnapshotDiffer()

    def seed(
        self,
        *,
        settings: HistorySeedSettings,
        day: date | None = None,
    ) -> HistorySeedResult:
        if not settings.force and self.state_store.get(HISTORY_SEED_STATE_KEY) is not None:
            return HistorySeedResult(skipped=True)

        if settings.empty_stop_months < 1:
            raise ValueError("empty_stop_months must be at least 1")

        end_period = settings.end_period or previous_closed_billing_period(day or utc_today())
        if settings.start_period is not None and settings.start_period > end_period:
            raise ValueError("start_period must be earlier than or equal to end_period")

        projects = self._target_projects(settings)
        self.project_writer.upsert_many(projects)

        periods_checked = 0
        periods_seeded = 0
        snapshots_saved = 0
        deltas_saved = 0
        tax_snapshots_saved = 0
        tax_deltas_saved = 0
        newest_seeded_period: str | None = None
        oldest_seeded_period: str | None = None
        empty_periods_seen = 0
        period = end_period

        while True:
            summary = self._seed_period(
                billing_period=period,
                organization_id=settings.organization_id,
                projects=projects,
                category_names=settings.category_names,
                source=settings.source,
            )
            periods_checked += 1
            snapshots_saved += summary.snapshots_saved
            deltas_saved += summary.deltas_saved
            tax_snapshots_saved += summary.tax_snapshots_saved
            tax_deltas_saved += summary.tax_deltas_saved

            if summary.has_data:
                periods_seeded += 1
                empty_periods_seen = 0
                newest_seeded_period = newest_seeded_period or period
                oldest_seeded_period = period
            else:
                empty_periods_seen += 1

            if settings.start_period is not None and period == settings.start_period:
                break
            if settings.start_period is None and empty_periods_seen >= settings.empty_stop_months:
                break
            period = previous_billing_period(period)

        self.state_store.set(
            HISTORY_SEED_STATE_KEY,
            f"{oldest_seeded_period or ''}:{newest_seeded_period or ''}",
        )
        return HistorySeedResult(
            projects_seen=len(projects),
            periods_checked=periods_checked,
            periods_seeded=periods_seeded,
            snapshots_saved=snapshots_saved,
            deltas_saved=deltas_saved,
            tax_snapshots_saved=tax_snapshots_saved,
            tax_deltas_saved=tax_deltas_saved,
            first_seeded_period=oldest_seeded_period,
            last_seeded_period=newest_seeded_period,
        )

    def _target_projects(self, settings: HistorySeedSettings) -> list[Project]:
        projects = self.project_reader.list_projects()
        if not settings.project_ids:
            return projects
        allowed_project_ids = set(settings.project_ids)
        return [project for project in projects if project.id in allowed_project_ids]

    def _seed_period(
        self,
        *,
        billing_period: str,
        organization_id: str,
        projects: list[Project],
        category_names: tuple[str, ...],
        source: str,
    ) -> PeriodSeedSummary:
        billing_day = billing_period_last_day(billing_period).isoformat()
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
                if not snapshot.lines:
                    continue
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
                deltas = self.differ.diff(
                    billing_day=billing_day,
                    current=snapshot,
                    previous=Snapshot(
                        billing_period=billing_period,
                        observed_at=snapshot.observed_at,
                        lines=(),
                    ),
                )
                self.daily_delta_store.upsert_many(
                    deltas,
                    current_snapshot_id=snapshot_id,
                    previous_snapshot_id=None,
                )
                deltas_saved += len(deltas)

        tax_summary = self._seed_tax_period(
            billing_period=billing_period,
            billing_day=billing_day,
            organization_id=organization_id,
            source=source,
        )
        return PeriodSeedSummary(
            snapshots_saved=snapshots_saved,
            deltas_saved=deltas_saved,
            tax_snapshots_saved=tax_summary.tax_snapshots_saved,
            tax_deltas_saved=tax_summary.tax_deltas_saved,
        )

    def _seed_tax_period(
        self,
        *,
        billing_period: str,
        billing_day: str,
        organization_id: str,
        source: str,
    ) -> PeriodSeedSummary:
        snapshot = self.tax_reader.list_taxes(
            billing_period=billing_period,
            organization_id=organization_id,
        )
        if not snapshot.lines:
            return PeriodSeedSummary()
        snapshot_id = self.tax_snapshot_store.save(snapshot, source=source)
        deltas = self.tax_differ.diff(
            billing_day=billing_day,
            current=snapshot,
            previous=TaxSnapshot(
                billing_period=billing_period,
                observed_at=snapshot.observed_at,
                organization_id=organization_id,
                lines=(),
            ),
        )
        self.tax_delta_store.upsert_many(
            deltas,
            current_tax_snapshot_id=snapshot_id,
            previous_tax_snapshot_id=None,
        )
        return PeriodSeedSummary(tax_snapshots_saved=1, tax_deltas_saved=len(deltas))

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
