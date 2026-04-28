from decimal import Decimal
from unittest import TestCase

from billing_collector.collection.differ import TaxSnapshotDiffer
from billing_collector.domain.models import TaxLine, TaxSnapshot


def _line(**overrides):
    base = {
        "billing_period": "2026-04",
        "organization_id": "org-a",
        "description": "VAT",
        "currency": "EUR",
        "rate": Decimal("0.2"),
        "total_tax_value": Decimal("10"),
    }
    base.update(overrides)
    return TaxLine(**base)


def _snapshot(*lines, billing_period="2026-04"):
    return TaxSnapshot.now(
        billing_period=billing_period,
        organization_id="org-a",
        lines=list(lines),
    )


class TaxDifferTests(TestCase):
    def test_first_tax_snapshot_is_baseline_only(self):
        differ = TaxSnapshotDiffer()

        self.assertEqual(
            differ.diff(
                billing_day="2026-04-28",
                current=_snapshot(_line()),
                previous=None,
            ),
            [],
        )

    def test_tax_diff(self):
        differ = TaxSnapshotDiffer()
        previous = _snapshot(_line(total_tax_value=Decimal("10")))
        current = _snapshot(_line(total_tax_value=Decimal("12.50")))

        deltas = differ.diff(
            billing_day="2026-04-28",
            current=current,
            previous=previous,
        )

        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0].delta_value, Decimal("2.50"))
        self.assertEqual(deltas[0].kind, "tax")

