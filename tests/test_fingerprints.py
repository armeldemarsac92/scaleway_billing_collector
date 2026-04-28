from decimal import Decimal
from unittest import TestCase

from billing_collector.domain.fingerprints import line_fingerprint
from billing_collector.domain.models import BillingLine


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
        "value": Decimal("12.34"),
        "billed_quantity": Decimal("42"),
    }
    base.update(overrides)
    return BillingLine(**base)


class FingerprintTests(TestCase):
    def test_fingerprint_ignores_value_changes(self):
        self.assertEqual(
            line_fingerprint(_line(value=Decimal("1"))),
            line_fingerprint(_line(value=Decimal("2"))),
        )

    def test_fingerprint_changes_when_sku_changes(self):
        self.assertNotEqual(line_fingerprint(_line()), line_fingerprint(_line(sku="/other")))
