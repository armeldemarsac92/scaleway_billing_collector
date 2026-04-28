from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.collection.differ import SnapshotDiffer
from billing_collector.domain.models import BillingLine, Snapshot
from billing_collector.metrics.collector import PrometheusMetricsCollector
from billing_collector.storage.database import SQLiteDatabase
from billing_collector.storage.repositories import DailyDeltaRepository, SnapshotRepository


def _line(**overrides):
    base = {
        "billing_period": "2026-04",
        "project_id": "project-a",
        "project_name": "Project A",
        "consumer_id": "org-a",
        "category_name": "Compute",
        "product_name": 'DEV1 "M"',
        "resource_name": "DEV1-M - fr-par-1",
        "sku": "/compute/dev1_m/run_par1",
        "unit": "minute",
        "currency": "EUR",
        "value": Decimal("10"),
        "billed_quantity": Decimal("100"),
    }
    base.update(overrides)
    return BillingLine(**base)


def _snapshot(*lines):
    return Snapshot.now(billing_period="2026-04", lines=list(lines))


class MetricsTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.database = SQLiteDatabase(f"{self.tmp.name}/collector.sqlite3")
        self.database.initialize()
        self.snapshots = SnapshotRepository(self.database)
        self.deltas = DailyDeltaRepository(self.database)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_cost_credit_and_quantity_counters(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("10"), billed_quantity=Decimal("100")))
        current = _snapshot(_line(value=Decimal("12.50"), billed_quantity=Decimal("125")))
        previous_id = self.snapshots.save(
            previous,
            scope_type="project",
            organization_id="org-a",
            project_id="project-a",
        )
        current_id = self.snapshots.save(
            current,
            scope_type="project",
            organization_id="org-a",
            project_id="project-a",
        )
        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-28",
                current=current,
                previous=previous,
            ),
            current_snapshot_id=current_id,
            previous_snapshot_id=previous_id,
        )

        output = PrometheusMetricsCollector(self.deltas).render()

        self.assertIn("# TYPE scaleway_billing_cost_euros_total counter", output)
        self.assertIn('project_id="project-a"', output)
        self.assertIn('product_name="DEV1 \\"M\\""', output)
        self.assertIn("scaleway_billing_cost_euros_total", output)
        self.assertIn(" 2.5", output)
        self.assertIn("scaleway_billing_billed_quantity_total", output)
        self.assertIn(" 25", output)

