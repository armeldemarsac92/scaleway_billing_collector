from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


BillingLineType = Literal[
    "resource_usage",
    "subscription",
    "contract",
    "credit",
    "free_tier_marker",
    "unknown",
]
BillingUsageType = Literal[
    "runtime",
    "capacity",
    "request",
    "token",
    "monthly",
    "plan",
    "monetary",
    "currency",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class BillingClassification:
    line_type: BillingLineType
    usage_type: BillingUsageType
    burn_rate_eligible: bool


class BillingLineClassifier:
    RUNTIME_UNITS = frozenset({"minute", "node_minute", "ip_minute", "hour"})
    CAPACITY_UNITS = frozenset({"gigabyte_hour", "gigabyte_minute", "gigabyte_month"})
    REQUEST_UNITS = frozenset({"request", "gb_s", "email"})

    def classify(
        self,
        *,
        category_name: str,
        product_name: str,
        resource_name: str,
        sku: str,
        unit: str,
        value: Decimal,
    ) -> BillingClassification:
        usage_type = self._usage_type(unit)
        return BillingClassification(
            line_type=self._line_type(
                category_name=category_name,
                product_name=product_name,
                resource_name=resource_name,
                sku=sku,
                unit=unit,
                value=value,
            ),
            usage_type=usage_type,
            burn_rate_eligible=usage_type == "runtime",
        )

    def _line_type(
        self,
        *,
        category_name: str,
        product_name: str,
        resource_name: str,
        sku: str,
        unit: str,
        value: Decimal,
    ) -> BillingLineType:
        normalized_category = category_name.strip().lower()
        normalized_sku = sku.strip().lower()
        normalized_unit = unit.strip().lower()
        marker_text = f"{product_name} {resource_name}".strip().lower()

        if value < 0 or normalized_sku.startswith("/offer/deducted/"):
            return "credit"
        if normalized_category == "contracts" or normalized_sku.startswith("/billing/"):
            return "contract"
        if normalized_category == "subscription" or normalized_sku.startswith("/subscription/"):
            return "subscription"
        if (
            value == 0
            and normalized_unit == "plan"
            and ("free tier" in marker_text or "offer" in marker_text)
        ):
            return "free_tier_marker"
        if value >= 0:
            return "resource_usage"
        return "unknown"

    def _usage_type(self, unit: str) -> BillingUsageType:
        normalized_unit = unit.strip().lower()
        if normalized_unit in self.RUNTIME_UNITS:
            return "runtime"
        if normalized_unit in self.CAPACITY_UNITS:
            return "capacity"
        if normalized_unit in self.REQUEST_UNITS:
            return "request"
        if normalized_unit == "token":
            return "token"
        if normalized_unit == "month":
            return "monthly"
        if normalized_unit == "plan":
            return "plan"
        if normalized_unit == "eur":
            return "monetary"
        if normalized_unit == "currency":
            return "currency"
        return "unknown"
