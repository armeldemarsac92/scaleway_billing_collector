from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.application.services.collection_models import HistorySeedSettings
from billing_collector.application.services.history_seed_service import HistorySeedService
from billing_collector.domain.models import BillingLine, Project, Snapshot, TaxLine, TaxSnapshot
from billing_collector.infrastructure.sqlite.collector_state_repository import (
    SqliteCollectorStateRepository,
)
from billing_collector.infrastructure.sqlite.daily_delta_repository import SqliteDailyDeltaRepository
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase
from billing_collector.infrastructure.sqlite.project_repository import SqliteProjectRepository
from billing_collector.infrastructure.sqlite.snapshot_repository import SqliteSnapshotRepository
from billing_collector.infrastructure.sqlite.tax_delta_repository import SqliteTaxDeltaRepository
from billing_collector.infrastructure.sqlite.tax_snapshot_repository import SqliteTaxSnapshotRepository


class FakeHistoryBillingClient:
    def __init__(self):
        self.values: dict[str, Decimal] = {}
        self.tax_values: dict[str, Decimal] = {}

    def list_projects(self) -> list[Project]:
        return [Project(id="project-a", name="Project A", organization_id="org-a")]

    def list_consumption(
        self,
        *,
        billing_period: str,
        project_id: str | None = None,
        category_name: str | None = None,
    ) -> Snapshot:
        value = self.values.get(billing_period)
        lines = []
        if value is not None:
            lines.append(
                BillingLine(
                    billing_period=billing_period,
                    project_id=project_id or "project-a",
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
            )
        return Snapshot.now(billing_period=billing_period, lines=lines)

    def list_taxes(self, *, billing_period: str, organization_id: str) -> TaxSnapshot:
        value = self.tax_values.get(billing_period)
        lines = []
        if value is not None:
            lines.append(
                TaxLine(
                    billing_period=billing_period,
                    organization_id=organization_id,
                    description="VAT",
                    currency="EUR",
                    rate=Decimal("0.2"),
                    total_tax_value=value,
                )
            )
        return TaxSnapshot.now(
            billing_period=billing_period,
            organization_id=organization_id,
            lines=lines,
        )


class HistorySeedTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.database = SQLiteDatabase(f"{self.tmp.name}/collector.sqlite3")
        self.database.initialize()
        self.client = FakeHistoryBillingClient()
        self.projects = SqliteProjectRepository(self.database)
        self.snapshots = SqliteSnapshotRepository(self.database)
        self.deltas = SqliteDailyDeltaRepository(self.database)
        self.tax_snapshots = SqliteTaxSnapshotRepository(self.database)
        self.tax_deltas = SqliteTaxDeltaRepository(self.database)
        self.state = SqliteCollectorStateRepository(self.database)
        self.service = HistorySeedService(
            project_reader=self.client,
            project_writer=self.projects,
            consumption_reader=self.client,
            tax_reader=self.client,
            snapshot_store=self.snapshots,
            daily_delta_store=self.deltas,
            tax_snapshot_store=self.tax_snapshots,
            tax_delta_store=self.tax_deltas,
            state_store=self.state,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_seeds_closed_months_as_month_level_deltas(self):
        self.client.values["2026-03"] = Decimal("10")
        self.client.values["2026-04"] = Decimal("12")
        self.client.tax_values["2026-04"] = Decimal("2.4")

        result = self.service.seed(
            settings=HistorySeedSettings(
                organization_id="org-a",
                start_period="2026-03",
                end_period="2026-04",
            )
        )

        self.assertFalse(result.skipped)
        self.assertEqual(result.periods_checked, 2)
        self.assertEqual(result.periods_seeded, 2)
        self.assertEqual(result.snapshots_saved, 2)
        self.assertEqual(result.deltas_saved, 2)
        self.assertEqual(result.tax_snapshots_saved, 1)
        self.assertEqual(result.tax_deltas_saved, 1)
        self.assertEqual(result.first_seeded_period, "2026-03")
        self.assertEqual(result.last_seeded_period, "2026-04")
        with self.database.connect() as connection:
            days = [
                row["billing_day"]
                for row in connection.execute(
                    "SELECT billing_day FROM daily_deltas ORDER BY billing_day"
                ).fetchall()
            ]
        self.assertEqual(days, ["2026-03-31", "2026-04-30"])
        self.assertEqual(self.deltas.list_billing_counters(), [])
        self.assertEqual(self.tax_deltas.list_tax_counters(), [])

    def test_skips_after_successful_seed_marker(self):
        self.client.values["2026-04"] = Decimal("12")
        self.service.seed(
            settings=HistorySeedSettings(
                organization_id="org-a",
                start_period="2026-04",
                end_period="2026-04",
            )
        )

        result = self.service.seed(
            settings=HistorySeedSettings(
                organization_id="org-a",
                start_period="2026-04",
                end_period="2026-04",
            )
        )

        self.assertTrue(result.skipped)
        with self.database.connect() as connection:
            snapshot_count = connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        self.assertEqual(snapshot_count, 1)
