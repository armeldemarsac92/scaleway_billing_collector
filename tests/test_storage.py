from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from billing_collector.application.ports.repositories import SnapshotScope
from billing_collector.domain.differ import SnapshotDiffer
from billing_collector.domain.models import BillingLine, Snapshot
from billing_collector.infrastructure.sqlite.daily_delta_repository import SqliteDailyDeltaRepository
from billing_collector.infrastructure.sqlite.database import SQLiteDatabase
from billing_collector.infrastructure.sqlite.snapshot_repository import SqliteSnapshotRepository


def _line(**overrides):
    base = {
        "billing_period": "2026-04",
        "project_id": "project-a",
        "project_name": "Project A",
        "consumer_id": "org-a",
        "category_name": "Compute",
        "product_name": "DEV1-M",
        "resource_name": "DEV1-M - fr-par-1",
        "sku": "/compute/dev1_m/run_par1",
        "unit": "minute",
        "currency": "EUR",
        "value": Decimal("10"),
        "billed_quantity": Decimal("100"),
    }
    base.update(overrides)
    return BillingLine(**base)


def _snapshot(*lines, billing_period="2026-04"):
    return Snapshot.now(billing_period=billing_period, lines=list(lines))


class StorageTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.database = SQLiteDatabase(f"{self.tmp.name}/collector.sqlite3")
        self.database.initialize()
        self.snapshots = SqliteSnapshotRepository(self.database)
        self.deltas = SqliteDailyDeltaRepository(self.database)

    def tearDown(self):
        self.tmp.cleanup()

    def test_saves_and_loads_previous_snapshot_for_scope(self):
        previous_id = self.snapshots.save(
            _snapshot(_line(value=Decimal("10"))),
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="test",
        )
        current_id = self.snapshots.save(
            _snapshot(_line(value=Decimal("12"))),
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="test",
        )

        previous = self.snapshots.previous_for_scope(
            SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            before_snapshot_id=current_id,
        )

        self.assertIsNotNone(previous)
        self.assertEqual(previous.id, previous_id)
        self.assertEqual(previous.snapshot.lines[0].value, Decimal("10"))

    def test_daily_delta_upsert_is_idempotent(self):
        differ = SnapshotDiffer()
        previous_id = self.snapshots.save(
            _snapshot(_line(value=Decimal("10"))),
            scope=SnapshotScope(
                billing_period="2026-04",
                scope_type="project",
                organization_id="org-a",
                project_id="project-a",
            ),
            source="test",
        )
        current = _snapshot(_line(value=Decimal("12.50"), billed_quantity=Decimal("125")))
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
        previous = self.snapshots.get(previous_id)
        deltas = differ.diff(
            billing_day="2026-04-28",
            current=current,
            previous=previous.snapshot,
        )

        self.deltas.upsert_many(
            deltas,
            current_snapshot_id=current_id,
            previous_snapshot_id=previous_id,
        )
        self.deltas.upsert_many(
            deltas,
            current_snapshot_id=current_id,
            previous_snapshot_id=previous_id,
        )

        self.assertEqual(self.deltas.count(), 1)
        self.assertEqual(self.deltas.list_billing_counters()[0].value, Decimal("2.5"))

    def test_daily_delta_accumulates_collection_intervals_for_same_day(self):
        differ = SnapshotDiffer()
        baseline = _snapshot(_line(value=Decimal("10"), billed_quantity=Decimal("100")))
        first_interval = _snapshot(
            _line(value=Decimal("12.50"), billed_quantity=Decimal("125"))
        )
        second_interval = _snapshot(
            _line(value=Decimal("15.25"), billed_quantity=Decimal("152.5"))
        )
        scope = SnapshotScope(
            billing_period="2026-04",
            scope_type="project",
            organization_id="org-a",
            project_id="project-a",
        )
        baseline_id = self.snapshots.save(baseline, scope=scope, source="test")
        first_interval_id = self.snapshots.save(first_interval, scope=scope, source="test")
        second_interval_id = self.snapshots.save(second_interval, scope=scope, source="test")

        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-28",
                current=first_interval,
                previous=baseline,
            ),
            current_snapshot_id=first_interval_id,
            previous_snapshot_id=baseline_id,
        )
        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-28",
                current=second_interval,
                previous=first_interval,
            ),
            current_snapshot_id=second_interval_id,
            previous_snapshot_id=first_interval_id,
        )

        counters = self.deltas.list_billing_counters()

        self.assertEqual(self.deltas.count(), 1)
        self.assertEqual(counters[0].kind, "cost")
        self.assertEqual(counters[0].value, Decimal("5.25"))
        self.assertEqual(counters[0].quantity, Decimal("52.5"))

    def test_positive_and_negative_intervals_use_separate_monotonic_counters(self):
        differ = SnapshotDiffer()
        baseline = _snapshot(_line(value=Decimal("10")))
        increased = _snapshot(_line(value=Decimal("12")))
        corrected = _snapshot(_line(value=Decimal("11")))
        scope = SnapshotScope(
            billing_period="2026-04",
            scope_type="project",
            organization_id="org-a",
            project_id="project-a",
        )
        baseline_id = self.snapshots.save(baseline, scope=scope, source="test")
        increased_id = self.snapshots.save(increased, scope=scope, source="test")
        corrected_id = self.snapshots.save(corrected, scope=scope, source="test")

        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-28",
                current=increased,
                previous=baseline,
            ),
            current_snapshot_id=increased_id,
            previous_snapshot_id=baseline_id,
        )
        self.deltas.upsert_many(
            differ.diff(
                billing_day="2026-04-28",
                current=corrected,
                previous=increased,
            ),
            current_snapshot_id=corrected_id,
            previous_snapshot_id=increased_id,
        )

        counters = {counter.kind: counter.value for counter in self.deltas.list_billing_counters()}

        self.assertEqual(counters["cost"], Decimal("2.0"))
        self.assertEqual(counters["credit"], Decimal("1.0"))

    def test_billing_counter_reader_sums_absolute_credit_values(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("10")))
        current = _snapshot(_line(value=Decimal("7.25")))
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

        counters = self.deltas.list_billing_counters()

        self.assertEqual(len(counters), 1)
        self.assertEqual(counters[0].kind, "credit")
        self.assertEqual(counters[0].value, Decimal("2.75"))
        self.assertEqual(counters[0].billing_line_type, "resource_usage")
        self.assertEqual(counters[0].billing_usage_type, "runtime")
        self.assertTrue(counters[0].burn_rate_eligible)
