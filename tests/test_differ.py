from decimal import Decimal
from unittest import TestCase

from billing_collector.collection.differ import SnapshotDiffer
from billing_collector.domain.models import BillingLine, Snapshot


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


class DifferTests(TestCase):
    def test_first_snapshot_is_baseline_only(self):
        differ = SnapshotDiffer()
        current = _snapshot(_line(value=Decimal("10")))

        self.assertEqual(
            differ.diff(billing_day="2026-04-28", current=current, previous=None),
            [],
        )

    def test_diff_positive_cost(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("10"), billed_quantity=Decimal("100")))
        current = _snapshot(_line(value=Decimal("12.50"), billed_quantity=Decimal("125")))

        deltas = differ.diff(
            billing_day="2026-04-28",
            current=current,
            previous=previous,
        )

        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0].delta_value, Decimal("2.50"))
        self.assertEqual(deltas[0].delta_quantity, Decimal("25"))
        self.assertEqual(deltas[0].kind, "cost")

    def test_diff_negative_credit(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(value=Decimal("10")))
        current = _snapshot(_line(value=Decimal("7.25")))

        deltas = differ.diff(
            billing_day="2026-04-28",
            current=current,
            previous=previous,
        )

        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0].delta_value, Decimal("-2.75"))
        self.assertEqual(deltas[0].absolute_value, Decimal("2.75"))
        self.assertEqual(deltas[0].kind, "credit")

    def test_does_not_diff_across_billing_periods(self):
        differ = SnapshotDiffer()
        previous = _snapshot(_line(billing_period="2026-03"), billing_period="2026-03")
        current = _snapshot(_line(billing_period="2026-04"), billing_period="2026-04")

        self.assertEqual(
            differ.diff(
                billing_day="2026-04-01",
                current=current,
                previous=previous,
            ),
            [],
        )
