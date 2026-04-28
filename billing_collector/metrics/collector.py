from __future__ import annotations

from decimal import Decimal

from billing_collector.storage.repositories import CounterValue, DailyDeltaRepository


class PrometheusMetricsCollector:
    def __init__(self, delta_repository: DailyDeltaRepository) -> None:
        self.delta_repository = delta_repository

    def render(self) -> str:
        counters = self.delta_repository.counter_values()
        lines: list[str] = [
            "# HELP scaleway_billing_cost_euros_total Reconstructed cumulative Scaleway billing costs in euros.",
            "# TYPE scaleway_billing_cost_euros_total counter",
            "# HELP scaleway_billing_credit_euros_total Reconstructed cumulative Scaleway billing credits in euros.",
            "# TYPE scaleway_billing_credit_euros_total counter",
            "# HELP scaleway_billing_billed_quantity_total Reconstructed cumulative Scaleway billed quantity.",
            "# TYPE scaleway_billing_billed_quantity_total counter",
        ]

        for counter in counters:
            metric_name = self._metric_name(counter)
            lines.append(
                f"{metric_name}{self._labels(counter)} {self._format_decimal(counter.value)}"
            )
            if counter.quantity is not None and counter.quantity >= 0:
                lines.append(
                    "scaleway_billing_billed_quantity_total"
                    f"{self._labels(counter)} {self._format_decimal(counter.quantity)}"
                )

        lines.append("")
        return "\n".join(lines)

    def _metric_name(self, counter: CounterValue) -> str:
        if counter.kind == "credit":
            return "scaleway_billing_credit_euros_total"
        return "scaleway_billing_cost_euros_total"

    def _labels(self, counter: CounterValue) -> str:
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
        rendered = ",".join(
            f'{name}="{self._escape_label_value(value)}"' for name, value in labels.items()
        )
        return f"{{{rendered}}}"

    def _escape_label_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def _format_decimal(self, value: Decimal) -> str:
        return format(value.normalize(), "f")

