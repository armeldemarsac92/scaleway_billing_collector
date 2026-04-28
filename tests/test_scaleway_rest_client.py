import json
from decimal import Decimal
from unittest import TestCase

import httpx

from billing_collector.scaleway.client import BillingAuthenticationError
from billing_collector.scaleway.rest_client import ScalewayRestBillingClient


class ScalewayRestBillingClientTests(TestCase):
    def test_list_consumption_parses_project_and_category_filtered_rows(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "consumptions": [
                        {
                            "value": {
                                "currency_code": "EUR",
                                "units": 26,
                                "nanos": 220_000_000,
                            },
                            "product_name": "DEV1-M",
                            "resource_name": "DEV1-M - fr-par-1",
                            "sku": "/compute/dev1_m/run_par1",
                            "project_id": "project-a",
                            "category_name": "Compute",
                            "unit": "minute",
                            "billed_quantity": "1324",
                            "consumer_id": "org-a",
                        }
                    ],
                    "total_count": 1,
                },
            )

        client = ScalewayRestBillingClient(
            secret_key="secret",
            organization_id="org-a",
            client=httpx.Client(
                base_url="https://api.scaleway.test",
                transport=httpx.MockTransport(handler),
            ),
        )

        snapshot = client.list_consumption(
            billing_period="2026-04",
            project_id="project-a",
            category_name="Compute",
        )

        self.assertEqual(len(snapshot.lines), 1)
        self.assertEqual(snapshot.lines[0].value, Decimal("26.22"))
        self.assertEqual(snapshot.lines[0].billed_quantity, Decimal("1324"))
        self.assertIn("project_id=project-a", str(requests[0].url))
        self.assertIn("category_name=Compute", str(requests[0].url))

    def test_list_projects_paginates_until_total_count(self):
        def handler(request: httpx.Request) -> httpx.Response:
            page = request.url.params["page"]
            payload = {
                "projects": [
                    {
                        "id": f"project-{page}",
                        "name": f"Project {page}",
                        "organization_id": "org-a",
                    }
                ],
                "total_count": 2,
            }
            return httpx.Response(200, content=json.dumps(payload).encode())

        client = ScalewayRestBillingClient(
            secret_key="secret",
            organization_id="org-a",
            page_size=1,
            client=httpx.Client(
                base_url="https://api.scaleway.test",
                transport=httpx.MockTransport(handler),
            ),
        )

        projects = client.list_projects()

        self.assertEqual([project.id for project in projects], ["project-1", "project-2"])

    def test_list_taxes_parses_org_level_tax_rows(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "taxes": [
                        {
                            "description": "VAT",
                            "currency": "EUR",
                            "rate": 0.2,
                            "total_tax_value": 1492.31,
                        }
                    ],
                    "total_count": 1,
                },
            )

        client = ScalewayRestBillingClient(
            secret_key="secret",
            organization_id="org-a",
            client=httpx.Client(
                base_url="https://api.scaleway.test",
                transport=httpx.MockTransport(handler),
            ),
        )

        snapshot = client.list_taxes(billing_period="2026-04", organization_id="org-a")

        self.assertEqual(snapshot.lines[0].total_tax_value, Decimal("1492.31"))
        self.assertEqual(snapshot.lines[0].rate, Decimal("0.2"))

    def test_authentication_errors_are_normalized(self):
        client = ScalewayRestBillingClient(
            secret_key="secret",
            organization_id="org-a",
            client=httpx.Client(
                base_url="https://api.scaleway.test",
                transport=httpx.MockTransport(lambda request: httpx.Response(403)),
            ),
        )

        with self.assertRaises(BillingAuthenticationError):
            client.list_projects()

