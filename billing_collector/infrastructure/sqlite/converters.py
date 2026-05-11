from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def decimal_to_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def decimal_from_text(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)

