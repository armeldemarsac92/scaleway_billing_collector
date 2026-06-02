# Grafana PromQL

These queries assume Grafana queries Prometheus or Thanos. They show live collector
time series from the moment Prometheus starts scraping.

## Net Cost Over Dashboard Range

```promql
sum(increase(scaleway_billing_cost_euros_total[$__range]))
-
sum(increase(scaleway_billing_credit_euros_total[$__range]))
```

## Current Cumulative Collector Total

This shows the net amount collected since the collector's local baseline.

```promql
sum(scaleway_billing_cost_euros_total)
-
sum(scaleway_billing_credit_euros_total)
```

## Intraday Net Cost Variation

Use this in a time-series panel to see which collection intervals consumed the most.
The visible precision is bounded by the collector interval and Scaleway's own billing
update cadence.

```promql
sum(
  increase(scaleway_billing_cost_euros_total[$__rate_interval])
)
-
sum(
  increase(scaleway_billing_credit_euros_total[$__rate_interval])
)
```

## Net Cost By Project

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total[$__range])
)
-
sum by (project_name) (
  increase(scaleway_billing_credit_euros_total[$__range])
)
```

## Net Cost By Category

```promql
sum by (category_name) (
  increase(scaleway_billing_cost_euros_total[$__range])
)
-
sum by (category_name) (
  increase(scaleway_billing_credit_euros_total[$__range])
)
```

## Runtime Hourly Burn Rate

Only runtime usage is included. Contracts, subscriptions, storage capacity, request/token usage, and free-tier markers are excluded.

```promql
sum(rate(
  scaleway_billing_resource_usage_euros_total{burn_rate_eligible="true"}[1h]
)) * 3600
```

## Cost By Billing Line Type

Use this to separate real usage from commercial lines such as Gold support or acceleration agreements.

```promql
sum by (billing_line_type) (
  increase(scaleway_billing_cost_euros_total[$__range])
)
```

## Resource-Only Cost

```promql
sum(increase(
  scaleway_billing_cost_euros_total{billing_line_type="resource_usage"}[$__range]
))
```

## Daily Cost Bars By Project

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total[1d])
)
-
sum by (project_name) (
  increase(scaleway_billing_credit_euros_total[1d])
)
```

Use a 1 day panel step or bar interval for daily cost evolution.

## Organization-Level Taxes

```promql
sum(increase(scaleway_billing_tax_euros_total[$__range]))
-
sum(increase(scaleway_billing_tax_credit_euros_total[$__range]))
```

Scaleway tax rows are organization-level in the tested API. Per-project tax-included values should be treated as estimated unless Scaleway exposes project-level taxes.

## Billed Quantity By SKU

```promql
sum by (sku, unit) (
  increase(scaleway_billing_billed_quantity_total[$__range])
)
```
