from datetime import date
from unittest import TestCase

from billing_collector.application.periods import (
    billing_period_for,
    billing_period_last_day,
    collection_window,
    next_billing_period,
    previous_billing_period,
    previous_closed_billing_period,
)


class PeriodTests(TestCase):
    def test_billing_period_for_date(self):
        self.assertEqual(billing_period_for(date(2026, 4, 28)), "2026-04")

    def test_previous_billing_period_handles_january(self):
        self.assertEqual(previous_billing_period("2026-01"), "2025-12")

    def test_next_billing_period_handles_december(self):
        self.assertEqual(next_billing_period("2026-12"), "2027-01")

    def test_billing_period_last_day_handles_leap_year(self):
        self.assertEqual(billing_period_last_day("2024-02"), date(2024, 2, 29))

    def test_previous_closed_billing_period(self):
        self.assertEqual(previous_closed_billing_period(date(2026, 5, 11)), "2026-04")

    def test_collection_window_includes_previous_period_during_backfill(self):
        window = collection_window(
            day=date(2026, 4, 3),
            previous_period_backfill_days=7,
        )

        self.assertEqual(window.billing_day, "2026-04-03")
        self.assertEqual(window.billing_periods, ("2026-04", "2026-03"))

    def test_collection_window_skips_previous_period_after_backfill(self):
        window = collection_window(
            day=date(2026, 4, 8),
            previous_period_backfill_days=7,
        )

        self.assertEqual(window.billing_periods, ("2026-04",))
