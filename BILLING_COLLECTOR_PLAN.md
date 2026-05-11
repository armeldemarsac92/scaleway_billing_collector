# Scaleway Billing Collector Plan

## Goal

Build a small Python service that reconstructs useful time-series billing data from the Scaleway Billing API.

Scaleway exposes billing consumption as month-to-date snapshots for a fixed billing period, not as arbitrary time-range records. The collector will fetch the current billing month regularly, compute the difference against the previous stored snapshot for the same billing period, persist that daily diff, and expose Prometheus metrics that Grafana/Thanos can query over time.

The implementation target is Kubernetes, scraped by the existing Prometheus stack and queried through the existing Thanos/Grafana setup.

## Confirmed Facts

### Scaleway Billing API

Live CLI checks confirmed:

- `scw billing consumption list project-id=<project-id> -o json` works.
- `scw billing consumption list category-name=Compute -o json` works.
- `scw billing consumption list project-id=<project-id> category-name=Compute -o json` works.
- Consumption rows include:
  - `value.currency_code`
  - `value.units`
  - `value.nanos`
  - `project_id`
  - `category_name`
  - `product_name`
  - `resource_name`
  - `sku`
  - `unit`
  - `billed_quantity`
  - `consumer_id`
- `scw billing consumption list-taxes -o json` works, but it does not accept `project-id` or `category-name`.
- Taxes should therefore be treated as organization/month-level exact values unless Scaleway later exposes project-level tax details.

Documentation references:

- Scaleway monthly consumption guide: https://www.scaleway.com/en/docs/billing/api-cli/retrieve-monthly-consumption/
- Scaleway Billing API: https://www.scaleway.com/en/developers/api/billing/
- Scaleway CLI billing docs: https://cli.scaleway.com/billing/

### Provider Adapter

The current implementation uses a small `httpx` REST adapter behind application-owned
reader ports, so the rest of the application is not coupled to Scaleway-specific
request or response models.

### Kubernetes And Observability

Read-only cluster inspection found:

- The central monitoring cluster has Thanos Query, Query Frontend, Store Gateway, Compactor, and Bucket Web.
- Thanos Receive is disabled in the central Thanos Helm release.
- The prod cluster has `kube-prometheus-stack` with Prometheus and a Thanos sidecar.
- Central Thanos Query already points to prod's external Thanos sidecar endpoint.
- The preferred ingestion path is therefore:

```text
billing-collector -> ServiceMonitor -> prod Prometheus -> Thanos sidecar -> central Thanos Query -> Grafana
```

Use Prometheus pull scraping. Do not use Pushgateway for the primary path.

Prometheus references:

- Exporter best practices: https://prometheus.io/docs/instrumenting/writing_exporters/
- Pushgateway guidance: https://prometheus.io/docs/practices/pushing/
- Thanos Receive docs: https://thanos.io/tip/components/receive.md/

## Non-Goals

- Do not build a direct Prometheus remote-write client in Python.
- Do not enable or modify Thanos Receive for this project.
- Do not store historical month-to-date totals as the canonical query source.
- Do not rely on Grafana to deduplicate repeated daily gauge samples.
- Do not attempt exact project-level tax allocation unless Scaleway exposes project-level tax data.

## Data Semantics

### Snapshot

A snapshot is the raw month-to-date state returned by Scaleway for a billing period at a specific fetch time.

Example:

```text
Billing period: 2026-04
Observed at: 2026-04-28T01:00:00Z
Project: Testing
Category: Compute
SKU: /compute/dev1_m/run_par1
Month-to-date value: 26.22 EUR
```

### Daily Diff

A daily diff is computed by comparing two snapshots from the same billing period.

```text
daily_diff = current_snapshot_month_to_date - previous_snapshot_month_to_date
```

The daily diff, not the month-to-date snapshot, is the canonical stored time-series event.

### Positive And Negative Deltas

Scaleway rows may be positive costs or negative credits/discounts. Month-to-date values can also move down because of corrections.

The collector should persist signed deltas, then expose them as separate positive counter families:

- Positive `delta_euros` becomes cost.
- Negative `delta_euros` becomes credit with absolute value.

This avoids invalid counter behavior while preserving net cost calculations.

## Prometheus Metric Model

Prometheus scrapes the exporter repeatedly. If the exporter exposes a daily diff gauge like this:

```text
scaleway_billing_daily_diff_euros{project="Testing"} 10
```

and Prometheus scrapes every 30 seconds, Prometheus stores many samples of `10` during the day. A query such as `sum_over_time(...[1d])` would overcount.

The exporter should therefore store only daily diffs in SQLite, but expose cumulative counters reconstructed from those stored diffs.

### Primary Metrics

```text
scaleway_billing_cost_euros_total{
  project_id,
  project_name,
  category_name,
  product_name,
  resource_name,
  sku,
  unit,
  currency
}
```

Counter reconstructed from positive stored deltas.

```text
scaleway_billing_credit_euros_total{
  project_id,
  project_name,
  category_name,
  product_name,
  resource_name,
  sku,
  unit,
  currency
}
```

Counter reconstructed from negative stored deltas, emitted as absolute values.

```text
scaleway_billing_billed_quantity_total{
  project_id,
  project_name,
  category_name,
  product_name,
  resource_name,
  sku,
  unit
}
```

Counter reconstructed from positive billed quantity deltas when quantities are numeric and meaningful.

```text
scaleway_billing_tax_euros_total{
  organization_id,
  currency,
  tax_description,
  tax_rate
}
```

Organization-level tax counter from `list-taxes`.

```text
scaleway_billing_tax_credit_euros_total{
  organization_id,
  currency,
  tax_description,
  tax_rate
}
```

Organization-level negative tax correction counter.

### Diagnostic Metrics

```text
scaleway_billing_collector_up
scaleway_billing_collector_last_success_timestamp_seconds
scaleway_billing_collector_last_failure_timestamp_seconds
scaleway_billing_collector_last_snapshot_lines
scaleway_billing_collector_last_delta_lines
scaleway_billing_collector_last_api_duration_seconds
```

### Optional Debug Metric

The latest stored daily diff can be exposed as a gauge for inspection only:

```text
scaleway_billing_last_daily_diff_euros{...}
```

Dashboards that aggregate over time should use `increase()` on counters, not `sum_over_time()` on this gauge.

## Grafana Query Examples

Net cost over the selected dashboard range:

```promql
sum(increase(scaleway_billing_cost_euros_total[$__range]))
-
sum(increase(scaleway_billing_credit_euros_total[$__range]))
```

Net cost by project over the selected range:

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total[$__range])
)
-
sum by (project_name) (
  increase(scaleway_billing_credit_euros_total[$__range])
)
```

Daily cost bars by project:

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total[1d])
)
-
sum by (project_name) (
  increase(scaleway_billing_credit_euros_total[1d])
)
```

Cost by category:

```promql
sum by (category_name) (
  increase(scaleway_billing_cost_euros_total[$__range])
)
-
sum by (category_name) (
  increase(scaleway_billing_credit_euros_total[$__range])
)
```

## Persistence Model

Use SQLite on a Kubernetes PVC for the first version.

Reasons:

- One writer.
- Small data volume.
- Simple operational footprint.
- Durable enough with a PVC.
- Easy to backup.

Use Postgres later only if HA, external SQL access, or concurrent writers become necessary.

SQLite path:

```text
/data/billing-collector.sqlite3
```

Run one replica only.

### Tables

#### projects

```text
id                  text primary key
name                text not null
organization_id     text not null
created_at          timestamp nullable
updated_at          timestamp nullable
last_seen_at        timestamp not null
```

#### snapshots

```text
id                  integer primary key
billing_period      text not null
observed_at         timestamp not null
scope_type          text not null       -- organization, project, project_category
organization_id     text not null
project_id          text nullable
category_name       text nullable
source              text not null       -- adapter source, for example scaleway-rest
raw_json            text not null
created_at          timestamp not null
```

#### snapshot_lines

```text
id                  integer primary key
snapshot_id         integer not null references snapshots(id)
billing_period      text not null
project_id          text not null
project_name        text nullable
consumer_id         text not null
category_name       text not null
product_name        text not null
resource_name       text not null
sku                 text not null
unit                text not null
currency            text not null
value_euros         numeric not null
billed_quantity     numeric nullable
line_fingerprint    text not null
raw_json            text not null
```

#### daily_deltas

```text
id                                  integer primary key
billing_day                         date not null
billing_period                      text not null
project_id                          text not null
project_name                        text nullable
consumer_id                         text not null
category_name                       text not null
product_name                        text not null
resource_name                       text not null
sku                                 text not null
unit                                text not null
currency                            text not null
delta_euros                         numeric not null
delta_quantity                      numeric nullable
kind                                text not null       -- cost, credit
line_fingerprint                    text not null
current_snapshot_id                 integer not null references snapshots(id)
previous_snapshot_id                integer nullable references snapshots(id)
created_at                          timestamp not null
updated_at                          timestamp not null
```

Unique constraint:

```text
billing_day, billing_period, line_fingerprint, kind
```

This makes collection idempotent.

#### tax_snapshots

```text
id                  integer primary key
billing_period      text not null
observed_at         timestamp not null
organization_id     text not null
raw_json            text not null
created_at          timestamp not null
```

#### tax_snapshot_lines

```text
id                  integer primary key
tax_snapshot_id     integer not null references tax_snapshots(id)
billing_period      text not null
organization_id     text not null
description         text not null
currency            text not null
rate                numeric nullable
total_tax_value     numeric not null
line_fingerprint    text not null
raw_json            text not null
```

#### tax_daily_deltas

```text
id                                  integer primary key
billing_day                         date not null
billing_period                      text not null
organization_id                     text not null
description                         text not null
currency                            text not null
rate                                numeric nullable
delta_euros                         numeric not null
kind                                text not null       -- tax, tax_credit
line_fingerprint                    text not null
current_tax_snapshot_id             integer not null references tax_snapshots(id)
previous_tax_snapshot_id            integer nullable references tax_snapshots(id)
created_at                          timestamp not null
updated_at                          timestamp not null
```

Unique constraint:

```text
billing_day, billing_period, line_fingerprint, kind
```

## Line Fingerprint

The line fingerprint should be a stable hash of dimensions that identify the same billing line across snapshots.

Consumption fingerprint input:

```text
billing_period
project_id
consumer_id
category_name
product_name
resource_name
sku
unit
currency
```

Tax fingerprint input:

```text
billing_period
organization_id
description
currency
rate
```

Use a deterministic SHA-256 hash over canonical JSON.

## Collection Algorithm

### Daily Consumption Collection

1. Determine the billing period using Scaleway's billing convention.
   - Scaleway's FAQ states the billing period is a calendar month in UTC.
   - Use UTC for `billing_period` and `billing_day`.
2. List projects.
3. For each configured project:
   - Fetch current month consumption with `project_id`.
   - If configured, fetch by `project_id` and `category_name`.
   - Store the raw snapshot.
   - Normalize every row into `snapshot_lines`.
4. Find the previous snapshot for the same project/category scope and same billing period.
5. Diff current lines against previous lines by `line_fingerprint`.
6. Insert or replace `daily_deltas` for the computed `billing_day`.
7. Fetch org-level taxes.
8. Store and diff tax snapshots separately.
9. Update collector status metrics.

### First Run

On the first run for a scope and billing period:

- Store the snapshot.
- Do not produce a daily delta unless a `bootstrap_first_snapshot_as_delta` setting is explicitly enabled.

Default should be no bootstrap delta, because the collector cannot know how much of the current month happened on the first day it starts.

### Month Rollover

Never diff across billing periods.

On the first snapshot of a new month:

- Store baseline.
- Produce no consumption daily delta for the new month until the next snapshot.

### Late Corrections

For the first few days of a new month, continue fetching the previous billing period and diff it against its previous stored snapshot. This captures late corrections, credits, and invoice finalization changes.

Configuration:

```text
previous_period_backfill_days = 7
```

## API Client Strategy

Define an internal protocol/interface:

```python
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
    ) -> ConsumptionSnapshot:
        ...

class TaxReader(Protocol):
    def list_taxes(
        self,
        *,
        billing_period: str,
        organization_id: str,
    ) -> TaxSnapshot:
        ...
```

Implementations:

- `ScalewayRestBillingClient`
- `FakeBillingClient` for tests

The rest of the app depends only on application-owned reader ports.

## Configuration

Configuration is parsed in `billing_collector/config.py` with a small standard-library
settings object.

Environment variables:

```text
SCW_ACCESS_KEY
SCW_SECRET_KEY
SCW_ORGANIZATION_ID
SCW_API_URL=https://api.scaleway.com
BILLING_COLLECTOR_DATABASE_URL=sqlite:////data/billing-collector.sqlite3
BILLING_COLLECTOR_BIND_HOST=0.0.0.0
BILLING_COLLECTOR_BIND_PORT=9503
BILLING_COLLECTOR_SCHEDULE_CRON=15 1 * * *
BILLING_COLLECTOR_TIMEZONE=UTC
BILLING_COLLECTOR_PREVIOUS_PERIOD_BACKFILL_DAYS=7
BILLING_COLLECTOR_PROJECT_IDS=
BILLING_COLLECTOR_CATEGORY_NAMES=
BILLING_COLLECTOR_BOOTSTRAP_FIRST_SNAPSHOT_AS_DELTA=false
```

`PROJECT_IDS` empty means all projects returned by the account API.

`CATEGORY_NAMES` empty means all categories in a single project-level request. If set, the collector can fetch individual project/category scopes.

## Python Package Structure

```text
billing_collector/
  __init__.py
  app.py
  config.py
  cli.py
  domain/
    models.py
    money.py
    fingerprints.py
    differ.py
  application/
    periods.py
    ports/
      billing.py
      repositories.py
    services/
      billing_collection_service.py
      collection_models.py
      consumption_collection_service.py
      tax_collection_service.py
  infrastructure/
    metrics/
      prometheus_metrics_renderer.py
    scaleway/
      rest_billing_client.py
    scheduling/
      interval_scheduler.py
    sqlite/
      converters.py
      database.py
      daily_delta_repository.py
      project_repository.py
      snapshot_repository.py
      tax_delta_repository.py
      tax_snapshot_repository.py
    web/
      metrics_server.py
tests/
  test_money.py
  test_fingerprints.py
  test_differ.py
  test_idempotency.py
  test_metrics.py
```

## SOLID Principles

### Single Responsibility Principle

Each class/module should have one reason to change:

- API clients fetch Scaleway data only.
- Differ computes deltas only.
- Application services orchestrate one use case each.
- Repository adapters persist or project stored data through application-owned ports.
- Metrics renderer converts counter projections to Prometheus exposition text only.
- Scheduler triggers collection only.

Avoid "god services" that fetch, normalize, diff, persist, and expose metrics in one class.

### Open/Closed Principle

The collector should be open to extension without rewriting core logic:

- Add another billing provider adapter without changing collection services.
- Add Postgres support without changing the differ.
- Add more metric families behind metric read ports.
- Add new billing scopes by extending configuration and client adapters.

Use interfaces/protocols at the boundaries.

### Liskov Substitution Principle

Any implementation of the billing reader ports must behave consistently:

- `ScalewayRestBillingClient` and test fakes return the same domain models.
- Callers should not need to know which implementation they received.
- Errors should be normalized into application exceptions such as `BillingProviderError`,
  `BillingProviderAuthenticationError`, and `BillingProviderRateLimitError`.

### Interface Segregation Principle

Do not force callers to depend on methods they do not use:

- `ProjectReader`, `ConsumptionReader`, and `TaxReader` for provider reads.
- `SnapshotStore`, `DailyDeltaStore`, `TaxSnapshotStore`, and `TaxDeltaStore` for writes.
- `BillingCounterReader` and `TaxCounterReader` for metric projections.
- `CollectorStatusRepository` or status service for health state.

Keep interfaces small and purpose-specific.

### Dependency Inversion Principle

High-level policy should not depend on low-level details:

- Collection services depend on application-owned ports, not Scaleway or SQLite classes.
- `PrometheusMetricsRenderer` depends on read ports, not SQLite internals.
- Application composition wires concrete dependencies in `app.py` or `cli.py`.

This keeps business logic testable without Scaleway credentials, Kubernetes, or a real database.

## Kubernetes Deployment Plan

Deploy in prod `monitoring` namespace unless there is a reason to centralize it elsewhere.

Resources:

- `Secret` for Scaleway credentials.
- `ConfigMap` for non-secret settings.
- `PersistentVolumeClaim` for SQLite.
- `Deployment` with one replica.
- `Service` exposing `/metrics`.
- `ServiceMonitor` with label `release: kube-prometheus-stack`.

ServiceMonitor should follow the existing prod pattern:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames:
      - monitoring
  selector:
    matchLabels:
      app: scaleway-billing-collector
  endpoints:
    - port: metrics
      path: /metrics
      interval: 60s
```

Security:

- Run as non-root.
- Read-only root filesystem if possible.
- Writable mount only for `/data`.
- No Kubernetes API RBAC needed by the app.
- Scaleway API key should have `BillingReadOnly` and project listing permissions.

## Health Endpoints

Expose:

```text
/healthz
/readyz
/metrics
```

Readiness should fail if:

- Database cannot be opened.
- No successful collection has occurred and startup grace period has elapsed.

Liveness should only fail for unrecoverable local process issues.

## Testing Strategy

### Unit Tests

- Money conversion from `units` and `nanos`, including negative values.
- Fingerprint stability.
- Diff when lines are added.
- Diff when lines disappear.
- Diff when lines decrease.
- First-run baseline behavior.
- Month rollover behavior.
- Tax diff behavior.
- Counter reconstruction from stored deltas.

### Integration Tests

- SQLite repository idempotency.
- Full collection flow with `FakeBillingClient`.
- `/metrics` output includes expected counter values.

### Manual Verification

Use Scaleway CLI for one project/category sample and compare with the collector's normalized values.

Do not commit real API responses if they contain sensitive organization details.

## Git Guidance And Implementation Slices

Keep changes in small, reviewable slices. Each slice should be independently testable and should avoid mixing unrelated concerns.

### Slice 1: Project Skeleton

Branch:

```text
feature/billing-collector-skeleton
```

Files:

- `pyproject.toml`
- package skeleton
- lint/test configuration
- basic README or plan link

Commit guidance:

```text
chore: scaffold billing collector project
```

Definition of done:

- `pytest` runs.
- package imports.
- no Scaleway API calls yet.

### Slice 2: Domain Models And Diff Logic

Branch:

```text
feature/billing-collector-domain-diff
```

Files:

- domain models
- money conversion
- fingerprinting
- differ
- unit tests

Commit guidance:

```text
feat: add billing domain models and diffing
```

Definition of done:

- Diff tests cover positive, negative, added, removed, and first-run cases.

### Slice 3: Persistence

Branch:

```text
feature/billing-collector-storage
```

Files:

- SQLAlchemy models
- repository interfaces
- SQLite implementation
- migration/bootstrap code
- repository tests

Commit guidance:

```text
feat: persist billing snapshots and daily deltas
```

Definition of done:

- Idempotency unique constraints tested.
- Counter reconstruction query tested.

### Slice 4: Scaleway Client

Branch:

```text
feature/billing-collector-scaleway-client
```

Files:

- REST billing client
- client adapter tests with mocked responses

Commit guidance:

```text
feat: add Scaleway billing client adapter
```

Definition of done:

- Provider integration is isolated behind application reader ports.
- Mocked tests do not require real credentials.
- Pagination is handled.

### Slice 5: Collection Service

Branch:

```text
feature/billing-collector-collection-service
```

Files:

- normalizer
- collection service
- scheduler or collect-now command
- service tests using fake client

Commit guidance:

```text
feat: collect and store daily billing deltas
```

Definition of done:

- End-to-end fake collection writes expected deltas.
- Month rollover and previous-period backfill are covered.

### Slice 6: Prometheus Exporter

Branch:

```text
feature/billing-collector-prometheus-exporter
```

Files:

- metrics collector
- HTTP server
- health endpoints
- metrics tests

Commit guidance:

```text
feat: expose billing deltas as Prometheus metrics
```

Definition of done:

- `/metrics` emits valid OpenMetrics/Prometheus text.
- Counter values are reconstructed from stored diffs.

### Slice 7: Container And Kubernetes Manifests

Branch:

```text
feature/billing-collector-kubernetes
```

Files:

- `Dockerfile`
- Kubernetes manifests or Helm chart
- ServiceMonitor
- deployment documentation

Commit guidance:

```text
feat: add Kubernetes deployment for billing collector
```

Definition of done:

- Image builds locally.
- Manifests render.
- ServiceMonitor labels match prod Prometheus selectors.

### Slice 8: Dashboard And Runbook

Branch:

```text
feature/billing-collector-dashboard-runbook
```

Files:

- Grafana dashboard JSON or documented PromQL panels
- runbook
- alert examples

Commit guidance:

```text
docs: add billing collector dashboard and runbook
```

Definition of done:

- Queries use `increase()` on counters.
- Runbook explains first-run, month rollover, and correction behavior.

## Review Checklist

Before merging implementation:

- No credentials or raw sensitive billing payloads committed.
- All API access is read-only.
- All business logic has tests independent from Scaleway.
- Prometheus metrics avoid high-cardinality labels such as timestamps, UUIDs unrelated to billing dimensions, or raw resource IDs unless explicitly accepted.
- The app runs as a single replica with SQLite.
- The first-run behavior is documented.
- Negative corrections are represented without violating counter semantics.
- Tax limitations are explicit in docs and dashboards.

## Open Decisions

1. Whether to fetch all project consumption once per project, or also fetch per configured category.
   - Recommendation: fetch once per project first, because response rows already include `category_name`.
   - Use category filters only to reduce API payload size or implement category allowlists.

2. Whether to estimate project-level tax-included values.
   - Recommendation: exact untaxed per project/component plus exact org-level tax.
   - If project-level tax-included is required, add estimated tax allocation with a label such as `tax_allocation="proportional_estimate"`.

3. Whether the app should run a scheduler internally or be triggered by a Kubernetes CronJob.
   - Recommendation: long-running Deployment with internal scheduler and `/metrics`.
   - Alternative: CronJob plus separate exporter process reading the same PVC is more complex.

4. Whether to bootstrap the first snapshot as a delta.
   - Recommendation: no. First snapshot is baseline only.
