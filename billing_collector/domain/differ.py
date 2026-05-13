from __future__ import annotations

from decimal import Decimal

from billing_collector.domain.fingerprints import line_fingerprint, tax_fingerprint
from billing_collector.domain.models import (
    BillingLine,
    DailyDelta,
    Snapshot,
    TaxDailyDelta,
    TaxLine,
    TaxSnapshot,
)


class SnapshotDiffer:
    def diff(
        self,
        *,
        billing_day: str,
        current: Snapshot,
        previous: Snapshot | None,
    ) -> list[DailyDelta]:
        if previous is None:
            return []

        if current.billing_period != previous.billing_period:
            return []

        current_by_key = self._index(current.lines)
        previous_by_key = self._index(previous.lines)
        fingerprints = sorted(set(current_by_key) | set(previous_by_key))

        deltas: list[DailyDelta] = []
        for fingerprint in fingerprints:
            current_line = current_by_key.get(fingerprint)
            previous_line = previous_by_key.get(fingerprint)
            reference_line = current_line or previous_line
            if reference_line is None:
                continue

            current_value = current_line.value if current_line else Decimal("0")
            previous_value = previous_line.value if previous_line else Decimal("0")
            delta_value = current_value - previous_value

            current_quantity = current_line.billed_quantity if current_line else Decimal("0")
            previous_quantity = previous_line.billed_quantity if previous_line else Decimal("0")
            delta_quantity = self._delta_quantity(current_quantity, previous_quantity)

            if delta_value == 0 and (delta_quantity is None or delta_quantity == 0):
                continue

            deltas.append(
                DailyDelta(
                    billing_day=billing_day,
                    billing_period=current.billing_period,
                    project_id=reference_line.project_id,
                    project_name=reference_line.project_name,
                    consumer_id=reference_line.consumer_id,
                    category_name=reference_line.category_name,
                    product_name=reference_line.product_name,
                    resource_name=reference_line.resource_name,
                    sku=reference_line.sku,
                    unit=reference_line.unit,
                    currency=reference_line.currency,
                    delta_value=delta_value,
                    delta_quantity=delta_quantity,
                    line_fingerprint=fingerprint,
                    billing_line_type=reference_line.billing_line_type,
                    billing_usage_type=reference_line.billing_usage_type,
                    burn_rate_eligible=bool(reference_line.burn_rate_eligible),
                )
            )

        return deltas

    def _index(self, lines: tuple[BillingLine, ...]) -> dict[str, BillingLine]:
        return {line_fingerprint(line): line for line in lines}

    def _delta_quantity(
        self,
        current: Decimal | None,
        previous: Decimal | None,
    ) -> Decimal | None:
        if current is None or previous is None:
            return None
        return current - previous


class TaxSnapshotDiffer:
    def diff(
        self,
        *,
        billing_day: str,
        current: TaxSnapshot,
        previous: TaxSnapshot | None,
    ) -> list[TaxDailyDelta]:
        if previous is None:
            return []
        if current.billing_period != previous.billing_period:
            return []

        current_by_key = self._index(current.lines)
        previous_by_key = self._index(previous.lines)
        fingerprints = sorted(set(current_by_key) | set(previous_by_key))

        deltas: list[TaxDailyDelta] = []
        for fingerprint in fingerprints:
            current_line = current_by_key.get(fingerprint)
            previous_line = previous_by_key.get(fingerprint)
            reference_line = current_line or previous_line
            if reference_line is None:
                continue
            current_value = current_line.total_tax_value if current_line else Decimal("0")
            previous_value = previous_line.total_tax_value if previous_line else Decimal("0")
            delta_value = current_value - previous_value
            if delta_value == 0:
                continue
            deltas.append(
                TaxDailyDelta(
                    billing_day=billing_day,
                    billing_period=current.billing_period,
                    organization_id=reference_line.organization_id,
                    description=reference_line.description,
                    currency=reference_line.currency,
                    rate=reference_line.rate,
                    delta_value=delta_value,
                    line_fingerprint=fingerprint,
                )
            )

        return deltas

    def _index(self, lines: tuple[TaxLine, ...]) -> dict[str, TaxLine]:
        return {tax_fingerprint(line): line for line in lines}
