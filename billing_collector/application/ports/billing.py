from __future__ import annotations

from typing import Protocol

from billing_collector.domain.models import Project, Snapshot, TaxSnapshot


class BillingProviderError(RuntimeError):
    """Base error raised by billing provider adapters."""


class BillingProviderAuthenticationError(BillingProviderError):
    """Raised when the billing provider rejects credentials."""


class BillingProviderRateLimitError(BillingProviderError):
    """Raised when the billing provider asks the collector to slow down."""


class ProjectReader(Protocol):
    def list_projects(self) -> list[Project]:
        ...


class ConsumptionReader(Protocol):
    def list_consumption(
        self,
        *,
        billing_period: str,
        project_id: str | None = None,
        category_name: str | None = None,
    ) -> Snapshot:
        ...


class TaxReader(Protocol):
    def list_taxes(
        self,
        *,
        billing_period: str,
        organization_id: str,
    ) -> TaxSnapshot:
        ...

