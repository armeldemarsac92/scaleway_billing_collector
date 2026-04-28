from decimal import Decimal
from unittest import TestCase

from billing_collector.domain.money import scaleway_money_to_decimal


class MoneyTests(TestCase):
    def test_scaleway_money_to_decimal_positive(self):
        self.assertEqual(scaleway_money_to_decimal(72, 820_000_000), Decimal("72.82"))

    def test_scaleway_money_to_decimal_negative_units_and_nanos(self):
        self.assertEqual(
            scaleway_money_to_decimal(-230, -760_000_000),
            Decimal("-230.76"),
        )

    def test_scaleway_money_to_decimal_negative_nanos_only(self):
        self.assertEqual(scaleway_money_to_decimal(0, -20_000_000), Decimal("-0.02"))
