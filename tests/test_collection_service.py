from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.application.services.billing_collection_service import BillingCollectionService
from billing_collector.application.services.collection_models import CollectionSettings
from billing_collector.application.services.consumption_collection_service import (
    ConsumptionCollectionService,
)
from billing_collector.application.services.tax_collection_service import TaxCollectionService
from billing_collector.domain.models import BillingLine, Project, Snapshot, TaxLine, TaxSnapshot
from billing_collector.infrastructure.sqlite.daily_delta_repository import SqliteDailyDeltaRepository
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase
from billing_collector.infrastructure.sqlite.project_repository import SqliteProjectRepository
from billing_collector.infrastructure.sqlite.snapshot_repository import SqliteSnapshotRepository
from billing_collector.infrastructure.sqlite.tax_delta_repository import SqliteTaxDeltaRepository
from billing_collector.infrastructure.sqlite.tax_snapshot_repository import SqliteTaxSnapshotRepository


class FakeBillingClient:
    def __init__(self):
        self.calls: list[tuple[str, str | None, str | None]] = []
        self.tax_calls: list[str] = []
        self.values: dict[tuple[str, str, str | None], Decimal] = {}
        self.tax_values: dict[str, Decimal] = {}

    def list_projects(self) -> list[Project]:
        return [
            Project(id="project-a", name="Project A", organization_id="org-a"),
            Project(id="project-b", name="Project B", organization_id="org-a"),
        ]

    def list_consumption(
        self,
        *,
        billing_period: str,
        project_id: str | None = None,
        category_name: str | None = None,
    ) -> Snapshot:
        if project_id is None:
            raise AssertionError("tests expect per-project collection")
        self.calls.append((billing_period, project_id, category_name))
        value = self.values.get((billing_period, project_id, category_name), Decimal("0"))
        return Snapshot.now(
            billing_period=billing_period,
            lines=[
                BillingLine(
                    billing_period=billing_period,
                    project_id=project_id,
                    consumer_id="org-a",
                    category_name=category_name or "Compute",
                    product_name="DEV1-M",
                    resource_name="DEV1-M - fr-par-1",
                    sku="/compute/dev1_m/run_par1",
                    unit="minute",
                    currency="EUR",
                    value=value,
                    billed_quantity=value * Decimal("10"),
                )
            ],
        )

    def list_taxes(self, *, billing_period: str, organization_id: str) -> TaxSnapshot:
        self.tax_calls.append(billing_period)
        return TaxSnapshot.now(
            billing_period=billing_period,
            organization_id=organization_id,
            lines=[
                TaxLine(
                    billing_period=billing_period,
                    organization_id=organization_id,
                    description="VAT",
                    currency="EUR",
                    rate=Decimal("0.2"),
                    total_tax_value=self.tax_values.get(billing_period, Decimal("0")),
                )
            ],
        )


class CollectionServiceTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.database = SQLiteDatabase(f"{self.tmp.name}/collector.sqlite3")
        self.database.initialize()
        self.client = FakeBillingClient()
        self.projects = SqliteProjectRepository(self.database)
        self.snapshots = SqliteSnapshotRepository(self.database)
        self.deltas = SqliteDailyDeltaRepository(self.database)
        self.tax_snapshots = SqliteTaxSnapshotRepository(self.database)
        self.tax_deltas = SqliteTaxDeltaRepository(self.database)
        self.consumption_collection_service = ConsumptionCollectionService(
            consumption_reader=self.client,
            snapshot_store=self.snapshots,
            daily_delta_store=self.deltas,
        )
        self.tax_collection_service = TaxCollectionService(
            tax_reader=self.client,
            tax_snapshot_store=self.tax_snapshots,
            tax_delta_store=self.tax_deltas,
        )
        self.service = BillingCollectionService(
            project_reader=self.client,
            project_writer=self.projects,
            consumption_collection_service=self.consumption_collection_service,
            tax_collection_service=self.tax_collection_service,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_uses_project_and_category_scope_and_writes_deltas(self):
        settings = CollectionSettings(
            organization_id="org-a",
            project_ids=("project-a",),
            category_names=("Compute",),
        )
        self.client.values[("2026-04", "project-a", "Compute")] = Decimal("10")
        self.client.tax_values["2026-04"] = Decimal("2")
        first = self.service.collect(settings=settings, day=date(2026, 4, 28))
        self.client.values[("2026-04", "project-a", "Compute")] = Decimal("12.50")
        self.client.tax_values["2026-04"] = Decimal("2.50")
        second = self.service.collect(settings=settings, day=date(2026, 4, 28))

        self.assertEqual(first.deltas_saved, 0)
        self.assertEqual(first.tax_deltas_saved, 0)
        self.assertEqual(second.deltas_saved, 1)
        self.assertEqual(second.tax_deltas_saved, 1)
        self.assertEqual(self.deltas.count(), 1)
        self.assertEqual(
            self.client.calls,
            [
                ("2026-04", "project-a", "Compute"),
                ("2026-04", "project-a", "Compute"),
            ],
        )
        counters = self.deltas.list_billing_counters()
        self.assertEqual(counters[0].project_name, "Project A")
        self.assertEqual(counters[0].value, Decimal("2.5"))
        self.assertEqual(self.tax_deltas.list_tax_counters()[0].value, Decimal("0.5"))

    def test_collect_backfills_previous_period_during_first_days(self):
        settings = CollectionSettings(
            organization_id="org-a",
            project_ids=("project-a",),
            previous_period_backfill_days=7,
        )

        self.service.collect(settings=settings, day=date(2026, 4, 3))

        self.assertEqual(
            self.client.calls,
            [
                ("2026-04", "project-a", None),
                ("2026-03", "project-a", None),
            ],
        )

    def test_collect_keeps_category_scopes_separate(self):
        settings = CollectionSettings(
            organization_id="org-a",
            project_ids=("project-a",),
            category_names=("Compute", "Storage"),
        )
        self.client.values[("2026-04", "project-a", "Compute")] = Decimal("10")
        self.client.values[("2026-04", "project-a", "Storage")] = Decimal("100")
        self.service.collect(settings=settings, day=date(2026, 4, 28))
        self.client.values[("2026-04", "project-a", "Compute")] = Decimal("12")
        self.client.values[("2026-04", "project-a", "Storage")] = Decimal("90")

        result = self.service.collect(settings=settings, day=date(2026, 4, 28))

        self.assertEqual(result.deltas_saved, 2)
        counters = {
            (counter.category_name, counter.kind): counter.value
            for counter in self.deltas.list_billing_counters()
        }
        self.assertEqual(counters[("Compute", "cost")], Decimal("2.0"))
        self.assertEqual(counters[("Storage", "credit")], Decimal("10.0"))

    def test_collect_does_not_diff_across_billing_periods(self):
        settings = CollectionSettings(
            organization_id="org-a",
            project_ids=("project-a",),
            previous_period_backfill_days=0,
        )
        self.client.values[("2026-04", "project-a", None)] = Decimal("10")
        april = self.service.collect(settings=settings, day=date(2026, 4, 30))
        self.client.values[("2026-05", "project-a", None)] = Decimal("2")
        may = self.service.collect(settings=settings, day=date(2026, 5, 1))

        self.assertEqual(april.deltas_saved, 0)
        self.assertEqual(may.deltas_saved, 0)
        self.assertEqual(self.deltas.count(), 0)
