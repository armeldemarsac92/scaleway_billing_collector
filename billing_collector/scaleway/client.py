from __future__ import annotations

from typing import Protocol

from billing_collector.domain.models import Project, Snapshot, TaxSnapshot


class BillingClientError(RuntimeError):
    pass


class BillingAuthenticationError(BillingClientError):
    pass


class BillingRateLimitError(BillingClientError):
    pass


class BillingClient(Protocol):
    def list_projects(self) -> list[Project]:
        ...

    def list_consumption(
        self,
        *,
        billing_period: str,
        project_id: str | None = None,
        category_name: str | None = None,
    ) -> Snapshot:
        ...

    def list_taxes(
        self,
        *,
        billing_period: str,
        organization_id: str,
    ) -> TaxSnapshot:
        ...

