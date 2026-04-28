from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from billing_collector.domain.models import BillingLine, Project, Snapshot, TaxLine, TaxSnapshot
from billing_collector.domain.money import scaleway_money_to_decimal
from billing_collector.scaleway.client import (
    BillingAuthenticationError,
    BillingClientError,
    BillingRateLimitError,
)


class ScalewayRestBillingClient:
    def __init__(
        self,
        *,
        secret_key: str,
        organization_id: str,
        api_url: str = "https://api.scaleway.com",
        page_size: int = 100,
        client: httpx.Client | None = None,
    ) -> None:
        self.organization_id = organization_id
        self.page_size = page_size
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={
                "X-Auth-Token": secret_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def list_projects(self) -> list[Project]:
        items = self._get_paginated(
            "/account/v3/projects",
            collection_key="projects",
            params={"organization_id": self.organization_id},
        )
        return [
            Project(
                id=item["id"],
                name=item["name"],
                organization_id=item["organization_id"],
            )
            for item in items
        ]

    def list_consumption(
        self,
        *,
        billing_period: str,
        project_id: str | None = None,
        category_name: str | None = None,
    ) -> Snapshot:
        params: dict[str, str] = {"billing_period": billing_period}
        if project_id is None:
            params["organization_id"] = self.organization_id
        else:
            params["project_id"] = project_id
        if category_name is not None:
            params["category_name"] = category_name

        items = self._get_paginated(
            "/billing/v2beta1/consumptions",
            collection_key="consumptions",
            params=params,
        )
        return Snapshot.now(
            billing_period=billing_period,
            lines=[self._consumption_line(billing_period, item) for item in items],
        )

    def list_taxes(
        self,
        *,
        billing_period: str,
        organization_id: str,
    ) -> TaxSnapshot:
        items = self._get_paginated(
            "/billing/v2beta1/taxes",
            collection_key="taxes",
            params={
                "billing_period": billing_period,
                "organization_id": organization_id,
            },
        )
        return TaxSnapshot.now(
            billing_period=billing_period,
            organization_id=organization_id,
            lines=[
                TaxLine(
                    billing_period=billing_period,
                    organization_id=organization_id,
                    description=item["description"],
                    currency=item["currency"],
                    rate=Decimal(str(item["rate"])) if item.get("rate") is not None else None,
                    total_tax_value=Decimal(str(item["total_tax_value"])),
                )
                for item in items
            ],
        )

    def _get_paginated(
        self,
        path: str,
        *,
        collection_key: str,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self.client.get(
                path,
                params={
                    **params,
                    "page": str(page),
                    "page_size": str(self.page_size),
                },
            )
            self._raise_for_status(response)
            payload = response.json()
            if isinstance(payload, list):
                return payload

            page_items = payload.get(collection_key, [])
            items.extend(page_items)
            total_count = payload.get("total_count")
            if total_count is None:
                if len(page_items) < self.page_size:
                    return items
            elif len(items) >= int(total_count):
                return items
            if not page_items:
                return items
            page += 1

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise BillingAuthenticationError(response.text)
        if response.status_code == 429:
            raise BillingRateLimitError(response.text)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BillingClientError(str(exc)) from exc

    def _consumption_line(self, billing_period: str, item: dict[str, Any]) -> BillingLine:
        value = item["value"]
        return BillingLine(
            billing_period=billing_period,
            project_id=item["project_id"],
            consumer_id=item["consumer_id"],
            category_name=item["category_name"],
            product_name=item["product_name"],
            resource_name=item["resource_name"],
            sku=item["sku"],
            unit=item["unit"],
            currency=value["currency_code"],
            value=scaleway_money_to_decimal(value["units"], value["nanos"]),
            billed_quantity=Decimal(item["billed_quantity"])
            if item.get("billed_quantity") is not None
            else None,
        )

