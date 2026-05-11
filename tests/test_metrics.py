from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.application.ports.repositories import SnapshotScope
from billing_collector.domain.differ import SnapshotDiffer
from billing_collector.domain.differ import TaxSnapshotDiffer
from billing_collector.domain.models import BillingLine, Snapshot, TaxLine, TaxSnapshot
from billing_collector.infrastructure.metrics.prometheus_metrics_renderer import (
    PrometheusMetricsRenderer,
)
from billing_collector.infrastructure.sqlite.daily_delta_repository import SqliteDailyDeltaRepository
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase
from billing_collector.infrastructure.sqlite.snapshot_repository import SqliteSnapshotRepository
from billing_collector.infrastructure.sqlite.tax_delta_repository import SqliteTaxDeltaRepository
from billing_collector.infrastructure.sqlite.tax_snapshot_repository import SqliteTaxSnapshotRepository


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
        self.snapshots = SqliteSnapshotRepository(self.database)
        self.deltas = SqliteDailyDeltaRepository(self.database)
        self.tax_snapshots = SqliteTaxSnapshotRepository(self.database)
        self.tax_deltas = SqliteTaxDeltaRepository(self.database)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_cost_credit_and_quantity_counters(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("10"), billed_quantity=Decimal("100")))
        current = _snapshot(_line(value=Decimal("12.50"), billed_quantity=Decimal("125")))
        previous_id = self.snapshots.save(
            previous,
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="test",
        )
        current_id = self.snapshots.save(
            current,
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="test",
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

        output = PrometheusMetricsRenderer(self.deltas).render()

        self.assertIn("# TYPE scaleway_billing_cost_euros_total counter", output)
        self.assertIn('project_id="project-a"', output)
        self.assertIn('product_name="DEV1 \\"M\\""', output)
        self.assertIn("scaleway_billing_cost_euros_total", output)
        self.assertIn(" 2.5", output)
        self.assertIn("scaleway_billing_billed_quantity_total", output)
        self.assertIn(" 25", output)

    def test_renders_tax_counters(self):
        previous = TaxSnapshot.now(
            billing_period="2026-04",
            organization_id="org-a",
            lines=[
                TaxLine(
                    billing_period="2026-04",
                    organization_id="org-a",
                    description="VAT",
                    currency="EUR",
                    rate=Decimal("0.2"),
                    total_tax_value=Decimal("10"),
                )
            ],
        )
        current = TaxSnapshot.now(
            billing_period="2026-04",
            organization_id="org-a",
            lines=[
                TaxLine(
                    billing_period="2026-04",
                    organization_id="org-a",
                    description="VAT",
                    currency="EUR",
                    rate=Decimal("0.2"),
                    total_tax_value=Decimal("12.50"),
                )
            ],
        )
        previous_id = self.tax_snapshots.save(previous, source="test")
        current_id = self.tax_snapshots.save(current, source="test")
        self.tax_deltas.upsert_many(
            TaxSnapshotDiffer().diff(
                billing_day="2026-04-28",
                current=current,
                previous=previous,
            ),
            current_tax_snapshot_id=current_id,
            previous_tax_snapshot_id=previous_id,
        )

        output = PrometheusMetricsRenderer(self.deltas, self.tax_deltas).render()

        self.assertIn("scaleway_billing_tax_euros_total", output)
        self.assertIn('organization_id="org-a"', output)
        self.assertIn('rate="0.2"', output)
        self.assertIn(" 2.5", output)

    def test_excludes_history_seeded_billing_deltas_from_prometheus_counters(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("0"), billed_quantity=Decimal("0")))
        current = _snapshot(_line(value=Decimal("12.50"), billed_quantity=Decimal("125")))
        previous_id = self.snapshots.save(
            previous,
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="scaleway-rest-history",
        )
        current_id = self.snapshots.save(
            current,
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="scaleway-rest-history",
        )
        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-30",
                current=current,
                previous=previous,
            ),
            current_snapshot_id=current_id,
            previous_snapshot_id=previous_id,
        )

        output = PrometheusMetricsRenderer(self.deltas).render()

        self.assertNotIn('project_id="project-a"', output)
        self.assertNotIn(" 12.5", output)

    def test_excludes_history_seeded_tax_deltas_from_prometheus_counters(self):
        previous = TaxSnapshot.now(
            billing_period="2026-04",
            organization_id="org-a",
            lines=[],
        )
        current = TaxSnapshot.now(
            billing_period="2026-04",
            organization_id="org-a",
            lines=[
                TaxLine(
                    billing_period="2026-04",
                    organization_id="org-a",
                    description="VAT",
                    currency="EUR",
                    rate=Decimal("0.2"),
                    total_tax_value=Decimal("2.50"),
                )
            ],
        )
        previous_id = self.tax_snapshots.save(previous, source="scaleway-rest-history")
        current_id = self.tax_snapshots.save(current, source="scaleway-rest-history")
        self.tax_deltas.upsert_many(
            TaxSnapshotDiffer().diff(
                billing_day="2026-04-30",
                current=current,
                previous=previous,
            ),
            current_tax_snapshot_id=current_id,
            previous_tax_snapshot_id=previous_id,
        )

        output = PrometheusMetricsRenderer(self.deltas, self.tax_deltas).render()

        self.assertNotIn('organization_id="org-a"', output)
        self.assertNotIn(" 2.5", output)
