from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    organization_id: str


@dataclass(frozen=True, slots=True)
class BillingLine:
    billing_period: str
    project_id: str
    consumer_id: str
    category_name: str
    product_name: str
    resource_name: str
    sku: str
    unit: str
    currency: str
    value: Decimal
    billed_quantity: Decimal | None
    project_name: str | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    billing_period: str
    observed_at: datetime
    lines: tuple[BillingLine, ...]

    @classmethod
    def now(cls, *, billing_period: str, lines: list[BillingLine]) -> "Snapshot":
        return cls(
            billing_period=billing_period,
            observed_at=datetime.now(UTC),
            lines=tuple(lines),
        )


@dataclass(frozen=True, slots=True)
class TaxLine:
    billing_period: str
    organization_id: str
    description: str
    currency: str
    rate: Decimal | None
    total_tax_value: Decimal


@dataclass(frozen=True, slots=True)
class TaxSnapshot:
    billing_period: str
    observed_at: datetime
    organization_id: str
    lines: tuple[TaxLine, ...]

    @classmethod
    def now(
        cls,
        *,
        billing_period: str,
        organization_id: str,
        lines: list[TaxLine],
    ) -> "TaxSnapshot":
        return cls(
            billing_period=billing_period,
            observed_at=datetime.now(UTC),
            organization_id=organization_id,
            lines=tuple(lines),
        )


@dataclass(frozen=True, slots=True)
class DailyDelta:
    billing_day: str
    billing_period: str
    project_id: str
    consumer_id: str
    category_name: str
    product_name: str
    resource_name: str
    sku: str
    unit: str
    currency: str
    delta_value: Decimal
    delta_quantity: Decimal | None
    line_fingerprint: str
    project_name: str | None = None

    @property
    def kind(self) -> str:
        return "cost" if self.delta_value >= 0 else "credit"

    @property
    def absolute_value(self) -> Decimal:
        return abs(self.delta_value)
