from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.collection.service import BillingCollectionService, CollectionSettings
from billing_collector.domain.models import BillingLine, Project, Snapshot, TaxSnapshot
from billing_collector.storage.database import SQLiteDatabase
from billing_collector.storage.repositories import (
    DailyDeltaRepository,
    ProjectRepository,
    SnapshotRepository,
)


class FakeBillingClient:
    def __init__(self):
        self.calls: list[tuple[str, str | None, str | None]] = []
        self.values: dict[tuple[str, str, str | None], Decimal] = {}

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
        return TaxSnapshot.now(
            billing_period=billing_period,
            organization_id=organization_id,
            lines=[],
        )


class CollectionServiceTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.database = SQLiteDatabase(f"{self.tmp.name}/collector.sqlite3")
        self.database.initialize()
        self.client = FakeBillingClient()
        self.projects = ProjectRepository(self.database)
        self.snapshots = SnapshotRepository(self.database)
        self.deltas = DailyDeltaRepository(self.database)
        self.service = BillingCollectionService(
            client=self.client,
            project_repository=self.projects,
            snapshot_repository=self.snapshots,
            delta_repository=self.deltas,
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
        first = self.service.collect(settings=settings, day=date(2026, 4, 28))
        self.client.values[("2026-04", "project-a", "Compute")] = Decimal("12.50")
        second = self.service.collect(settings=settings, day=date(2026, 4, 28))

        self.assertEqual(first.deltas_saved, 0)
        self.assertEqual(second.deltas_saved, 1)
        self.assertEqual(self.deltas.count(), 1)
        self.assertEqual(
            self.client.calls,
            [
                ("2026-04", "project-a", "Compute"),
                ("2026-04", "project-a", "Compute"),
            ],
        )
        counters = self.deltas.counter_values()
        self.assertEqual(counters[0].project_name, "Project A")
        self.assertEqual(counters[0].value, Decimal("2.5"))

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

