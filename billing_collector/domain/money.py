from __future__ import annotations

from decimal import Decimal

NANOS_PER_UNIT = Decimal("1000000000")


def scaleway_money_to_decimal(units: int, nanos: int) -> Decimal:
    """Convert Scaleway money fields to a decimal major-unit amount."""
    return Decimal(units) + (Decimal(nanos) / NANOS_PER_UNIT)


def decimal_to_metric_value(value: Decimal) -> float:
    return float(value)

