from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


def utc_today() -> date:
    return datetime.now(UTC).date()


def billing_period_for(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def previous_billing_period(period: str) -> str:
    year, month = [int(part) for part in period.split("-", maxsplit=1)]
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def next_billing_period(period: str) -> str:
    year, month = [int(part) for part in period.split("-", maxsplit=1)]
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def billing_period_last_day(period: str) -> date:
    next_period = next_billing_period(period)
    year, month = [int(part) for part in next_period.split("-", maxsplit=1)]
    return date(year, month, 1) - timedelta(days=1)


def previous_closed_billing_period(day: date) -> str:
    return previous_billing_period(billing_period_for(day))


def billing_periods_desc(*, start_period: str | None, end_period: str) -> tuple[str, ...]:
    if start_period is not None and start_period > end_period:
        raise ValueError("start_period must be earlier than or equal to end_period")
    periods: list[str] = []
    current = end_period
    while True:
        periods.append(current)
        if start_period is not None and current == start_period:
            return tuple(periods)
        current = previous_billing_period(current)


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
