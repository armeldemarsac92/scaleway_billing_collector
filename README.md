# Scaleway Billing Collector

Python service that snapshots Scaleway Billing API usage, computes daily deltas per project/component, and exposes Prometheus metrics for Thanos/Grafana.

## Why This Exists

The Scaleway Billing API returns consumption as month-to-date data for a fixed billing period such as `2026-04`. It does not expose arbitrary time-range usage records.

This collector turns those month-to-date snapshots into time-series data:

1. Fetch the current Scaleway billing period.
2. Store the raw month-to-date snapshot.
3. Compare it with the previous snapshot for the same billing period and scope.
4. Persist only the computed daily deltas.
5. Expose Prometheus counters reconstructed from those stored deltas.

Grafana can then query billing evolution over any range with PromQL `increase()`.

## Architecture

```text
Scaleway Billing API
        |
        v
scaleway-billing-collector
        |
        +-- SQLite PVC: raw snapshots and daily deltas
        |
        +-- /metrics
              |
              v
        Prometheus
              |
              v
          Thanos
              |
              v
          Grafana
```

The intended Kubernetes deployment is a single long-running pod:

- an internal scheduler performs collection periodically;
- `/metrics` is scraped by Prometheus;
- SQLite is stored on a persistent volume;
- one replica is required because SQLite is single-writer.

## Current Features

- Per-project Scaleway billing collection.
- Optional category filtering.
- Component-level labels from Scaleway rows:
  - project
  - category
  - product
  - resource
  - SKU
  - unit
  - currency
- Daily cost deltas from month-to-date snapshots.
- Separate credit counters for negative corrections, free-tier deductions, and discounts.
- Organization-level tax deltas from `list-taxes`.
- Previous-month backfill during the first days of a new month.
- SQLite persistence.
- Prometheus `/metrics` endpoint.
- `/healthz` and `/readyz` endpoints.
- Dockerfile and Kubernetes manifests with `ServiceMonitor`.

## Metric Model

The collector stores signed daily deltas internally, but exposes cumulative Prometheus counters.

This matters because Prometheus scrapes repeatedly. A daily diff exposed as a gauge would be sampled many times and would overcount with `sum_over_time()`.

Use `increase()` on counters instead.

Main metrics:

```text
scaleway_billing_cost_euros_total
scaleway_billing_credit_euros_total
scaleway_billing_billed_quantity_total
scaleway_billing_tax_euros_total
scaleway_billing_tax_credit_euros_total
```

Example net cost over a Grafana range:

```promql
sum(increase(scaleway_billing_cost_euros_total[$__range]))
-
sum(increase(scaleway_billing_credit_euros_total[$__range]))
```

More queries are documented in [docs/grafana-promql.md](docs/grafana-promql.md).

## First-Run Behavior

The first snapshot for a billing period is a baseline and does not produce a delta.

The first useful daily delta appears after the second snapshot for the same billing period and scope.

This avoids pretending the collector knows how much of the month happened before it started.

## Tax Limitation

The tested Scaleway tax endpoint accepts `billing-period` and `organization-id`, but not `project-id` or `category-name`.

The collector therefore exports exact organization-level tax counters. It does not claim exact project-level tax-included values.

## Configuration

Required environment variables:

```text
SCW_SECRET_KEY
SCW_ORGANIZATION_ID
```

Optional environment variables:

```text
SCW_API_URL=https://api.scaleway.com
BILLING_COLLECTOR_DATABASE_PATH=/data/billing-collector.sqlite3
BILLING_COLLECTOR_BIND_HOST=0.0.0.0
BILLING_COLLECTOR_BIND_PORT=9503
BILLING_COLLECTOR_PROJECT_IDS=
BILLING_COLLECTOR_CATEGORY_NAMES=
BILLING_COLLECTOR_PREVIOUS_PERIOD_BACKFILL_DAYS=7
BILLING_COLLECTOR_COLLECTION_INTERVAL_SECONDS=86400
BILLING_COLLECTOR_COLLECT_ON_START=true
```

`BILLING_COLLECTOR_PROJECT_IDS` and `BILLING_COLLECTOR_CATEGORY_NAMES` are comma-separated lists. Empty means all projects/categories returned by the Scaleway Billing API.

## Local Usage

Install the package in a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

Collect once:

```bash
SCW_SECRET_KEY=... \
SCW_ORGANIZATION_ID=... \
BILLING_COLLECTOR_DATABASE_PATH=./billing-collector.sqlite3 \
billing-collector collect-once
```

Serve metrics:

```bash
SCW_SECRET_KEY=... \
SCW_ORGANIZATION_ID=... \
BILLING_COLLECTOR_DATABASE_PATH=./billing-collector.sqlite3 \
billing-collector serve
```

Check endpoints:

```bash
curl http://localhost:9503/healthz
curl http://localhost:9503/readyz
curl http://localhost:9503/metrics
```

## Tests

The current test suite uses the Python standard library `unittest` plus mocked HTTP responses.

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Kubernetes

Create the secret:

```bash
kubectl -n monitoring create secret generic scaleway-billing-collector \
  --from-literal=SCW_SECRET_KEY='<scaleway-secret-key>' \
  --from-literal=SCW_ORGANIZATION_ID='<organization-id>'
```

Apply manifests:

```bash
kubectl apply -f deploy/kubernetes/scaleway-billing-collector.yaml
```

The manifests deploy:

- `ConfigMap`
- `PersistentVolumeClaim`
- `Deployment`
- `Service`
- `ServiceMonitor`

See [deploy/kubernetes/README.md](deploy/kubernetes/README.md) for deployment notes.

## Repository Docs

Operational docs:

- [Kubernetes deployment](deploy/kubernetes/README.md)
- [Runbook](docs/runbook.md)
- [Grafana PromQL](docs/grafana-promql.md)
- [Implementation plan](BILLING_COLLECTOR_PLAN.md)
