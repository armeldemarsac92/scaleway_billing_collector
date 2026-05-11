from __future__ import annotations

from decimal import Decimal

from billing_collector.application.ports.repositories import (
    BillingCounterReader,
    BillingCounterValue,
    TaxCounterReader,
    TaxCounterValue,
)


class PrometheusMetricsRenderer:
    def __init__(
        self,
        billing_counter_reader: BillingCounterReader,
        tax_counter_reader: TaxCounterReader | None = None,
    ) -> None:
        self.billing_counter_reader = billing_counter_reader
        self.tax_counter_reader = tax_counter_reader

    def render(self) -> str:
        lines: list[str] = [
            "# HELP scaleway_billing_cost_euros_total Reconstructed cumulative Scaleway billing costs in euros.",
            "# TYPE scaleway_billing_cost_euros_total counter",
            "# HELP scaleway_billing_credit_euros_total Reconstructed cumulative Scaleway billing credits in euros.",
            "# TYPE scaleway_billing_credit_euros_total counter",
            "# HELP scaleway_billing_billed_quantity_total Reconstructed cumulative Scaleway billed quantity.",
            "# TYPE scaleway_billing_billed_quantity_total counter",
            "# HELP scaleway_billing_tax_euros_total Reconstructed cumulative Scaleway organization-level taxes in euros.",
            "# TYPE scaleway_billing_tax_euros_total counter",
            "# HELP scaleway_billing_tax_credit_euros_total Reconstructed cumulative Scaleway organization-level tax credits in euros.",
            "# TYPE scaleway_billing_tax_credit_euros_total counter",
        ]

        for counter in self.billing_counter_reader.list_billing_counters():
            metric_name = self._billing_metric_name(counter)
            lines.append(
                f"{metric_name}{self._billing_labels(counter)} "
                f"{self._format_decimal(counter.value)}"
            )
            if counter.quantity is not None and counter.quantity >= 0:
                lines.append(
                    "scaleway_billing_billed_quantity_total"
                    f"{self._billing_labels(counter)} {self._format_decimal(counter.quantity)}"
                )

        if self.tax_counter_reader is not None:
            for counter in self.tax_counter_reader.list_tax_counters():
                metric_name = self._tax_metric_name(counter)
                lines.append(
                    f"{metric_name}{self._tax_labels(counter)} "
                    f"{self._format_decimal(counter.value)}"
                )

        lines.append("")
        return "\n".join(lines)

    def _billing_metric_name(self, counter: BillingCounterValue) -> str:
        if counter.kind == "credit":
            return "scaleway_billing_credit_euros_total"
        return "scaleway_billing_cost_euros_total"

    def _billing_labels(self, counter: BillingCounterValue) -> str:
        labels = {
            "project_id": counter.project_id,
            "project_name": counter.project_name or "",
            "consumer_id": counter.consumer_id,
            "category_name": counter.category_name,
            "product_name": counter.product_name,
            "resource_name": counter.resource_name,
            "sku": counter.sku,
            "unit": counter.unit,
            "currency": counter.currency,
        }
        return self._render_labels(labels)

    def _tax_metric_name(self, counter: TaxCounterValue) -> str:
        if counter.kind == "tax_credit":
            return "scaleway_billing_tax_credit_euros_total"
        return "scaleway_billing_tax_euros_total"

    def _tax_labels(self, counter: TaxCounterValue) -> str:
        labels = {
            "organization_id": counter.organization_id,
            "description": counter.description,
            "currency": counter.currency,
            "rate": str(counter.rate) if counter.rate is not None else "",
        }
        return self._render_labels(labels)

    def _render_labels(self, labels: dict[str, str]) -> str:
        rendered = ",".join(
            f'{name}="{self._escape_label_value(value)}"' for name, value in labels.items()
        )
        return f"{{{rendered}}}"

    def _escape_label_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def _format_decimal(self, value: Decimal) -> str:
        return format(value.normalize(), "f")

