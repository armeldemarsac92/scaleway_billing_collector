from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime


def utc_today() -> date:
    return datetime.now(UTC).date()


def billing_period_for(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def previous_billing_period(period: str) -> str:
    year, month = [int(part) for part in period.split("-", maxsplit=1)]
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


@dataclass(frozen=True, slots=True)
class BillingCollectionWindow:
    billing_day: str
    billing_periods: tuple[str, ...]


def collection_window(
    *,
    day: date,
    previous_period_backfill_days: int,
) -> BillingCollectionWindow:
    current = billing_period_for(day)
    periods = [current]
    if day.day <= previous_period_backfill_days:
        periods.append(previous_billing_period(current))
    return BillingCollectionWindow(
        billing_day=day.isoformat(),
        billing_periods=tuple(periods),
    )

