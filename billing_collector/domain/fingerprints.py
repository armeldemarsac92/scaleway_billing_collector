from __future__ import annotations

import hashlib
import json

from billing_collector.domain.models import BillingLine, TaxLine


def line_fingerprint(line: BillingLine) -> str:
    payload = {
        "billing_period": line.billing_period,
        "project_id": line.project_id,
        "consumer_id": line.consumer_id,
        "category_name": line.category_name,
        "product_name": line.product_name,
        "resource_name": line.resource_name,
        "sku": line.sku,
        "unit": line.unit,
        "currency": line.currency,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def tax_fingerprint(line: TaxLine) -> str:
    payload = {
        "billing_period": line.billing_period,
        "organization_id": line.organization_id,
        "description": line.description,
        "currency": line.currency,
        "rate": str(line.rate) if line.rate is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
