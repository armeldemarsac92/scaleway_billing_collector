# Billing Collector Runbook

## Runtime

The collector runs as one Kubernetes Deployment replica.

It performs two jobs:

- periodically fetches Scaleway month-to-date billing snapshots and stores local daily deltas in SQLite;
- serves `/metrics`, `/healthz`, and `/readyz` for Prometheus.

SQLite is stored on the `scaleway-billing-collector-data` PVC.

## Required Secret

Create this secret in the `monitoring` namespace:

```bash
kubectl -n monitoring create secret generic scaleway-billing-collector \
  --from-literal=SCW_SECRET_KEY='<scaleway-secret-key>' \
  --from-literal=SCW_ORGANIZATION_ID='<organization-id>'
```

The Scaleway key should be read-only for billing consumption and project listing.

## First Run

The first snapshot for a billing period is a baseline. It does not produce cost deltas because the collector cannot know how much of the month happened before it started.

The second snapshot for the same billing period produces the first daily deltas.

## Month Rollover

The collector never diffs across billing periods.

On the first collection of a new month:

- the new month gets a baseline snapshot;
- the previous month may still be collected for a few days to capture late corrections.

The default previous-period backfill window is seven days.

## Corrections And Credits

If a Scaleway month-to-date value decreases, the collector stores a negative delta and exports it through credit counters:

- `scaleway_billing_credit_euros_total`
- `scaleway_billing_tax_credit_euros_total`

Dashboards should subtract credits from costs.

## Billing Taxonomy

The collector classifies Scaleway consumption lines before exporting metrics:

- `billing_line_type="resource_usage"` for normal positive usage.
- `billing_line_type="subscription"` for support or subscription plans such as Gold support.
- `billing_line_type="contract"` for commercial contract lines such as acceleration agreements.
- `billing_line_type="credit"` for deducted offers and negative billing lines.

Use `burn_rate_eligible="true"` for hourly burn-rate panels. It is only set for runtime units: `minute`, `node_minute`, `ip_minute`, and `hour`.

## Useful Commands

Collect once locally or in a pod:

```bash
billing-collector collect-once
```

Serve metrics:

```bash
billing-collector serve
```

Check health:

```bash
curl http://localhost:9503/healthz
curl http://localhost:9503/readyz
curl http://localhost:9503/metrics
```

## Troubleshooting

If `/metrics` is empty except for HELP/TYPE lines, verify that:

- the first baseline collection has completed;
- at least two snapshots exist for the same billing period and scope;
- `SCW_SECRET_KEY` has billing read access;
- project filters in `BILLING_COLLECTOR_PROJECT_IDS` match real Scaleway project IDs.

If Prometheus does not scrape the collector, verify:

- the Service has label `app=scaleway-billing-collector`;
- the ServiceMonitor has label `release=kube-prometheus-stack`;
- the ServiceMonitor is in namespace `monitoring`;
- the endpoint port is named `metrics`.
