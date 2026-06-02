# Grafana PromQL

These queries assume Grafana queries Prometheus or Thanos. They show live collector
time series from the moment Prometheus starts scraping.

The billing metrics are Prometheus counters built from collector interval deltas.
Use `increase()` for costs over a selected time range. Do not use
`sum_over_time()` for billing totals, because Prometheus scrapes the same counter
value several times between collector runs.

## Dashboard Variables

Create Grafana variables from Prometheus labels:

```promql
label_values(scaleway_billing_cost_euros_total, project_name)
label_values(scaleway_billing_cost_euros_total, category_name)
label_values(scaleway_billing_cost_euros_total, product_name)
label_values(scaleway_billing_cost_euros_total, sku)
label_values(scaleway_billing_cost_euros_total, billing_line_type)
label_values(scaleway_billing_cost_euros_total, billing_usage_type)
```

Enable multi-value and include-all for label variables. In queries, use Grafana's
regex formatter:

```promql
project_name=~"${project_name:regex}"
category_name=~"${category_name:regex}"
product_name=~"${product_name:regex}"
```

For an "include non burn-rate eligible resources" switch, use a custom variable
named `burn_rate`:

| Label | Value |
| --- | --- |
| Runtime burn-rate only | `true` |
| Include non burn-rate eligible | `true|false` |

Use the raw formatter in PromQL:

```promql
burn_rate_eligible=~"${burn_rate:raw}"
```

Do not use `${burn_rate:regex}` for this variable, because Grafana escapes the
pipe and Prometheus rejects `true\|false`.

## Stat Panels

### Selected-Range Gross Cost

Use for a single Stat panel showing cost over the Grafana time range. This keeps
all selected billing line types and subtracts nothing.

```promql
sum(increase(scaleway_billing_cost_euros_total{
  project_name=~"${project_name:regex}",
  category_name=~"${category_name:regex}",
  product_name=~"${product_name:regex}",
  billing_line_type=~"${billing_line_type:regex}",
  billing_usage_type=~"${billing_usage_type:regex}",
  burn_rate_eligible=~"${burn_rate:raw}"
}[$__range]))
```

### Selected-Range Net Cost

Use for a single Stat panel showing cost minus credits over the Grafana time
range.

```promql
(
  sum(increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[$__range]))
  or vector(0)
)
-
(
  sum(increase(scaleway_billing_credit_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[$__range]))
  or vector(0)
)
```

### Current Cumulative Collector Total

Use this only as a diagnostic Stat panel. It is the net counter value since the
collector's local baseline, not the selected-range cost.

```promql
sum(scaleway_billing_cost_euros_total)
-
sum(scaleway_billing_credit_euros_total)
```

## Time-Series Panels

### Hourly Cost Evolution

Use this for a line graph or bar chart showing hourly cost deltas. Set the panel
minimum interval to `1h`. Keep the `sum by (...)` labels you want in the legend.

```promql
sum by (
  project_name,
  category_name,
  product_name,
  resource_name,
  unit,
  billing_usage_type,
  burn_rate_eligible
) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type="resource_usage",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[1h])
) > 0
```

Recommended legend:

```text
{{project_name}} / {{category_name}} / {{product_name}} / {{resource_name}} / {{unit}}
```

Avoid `{{resource_name}}` alone. Some Scaleway resources share generic names such
as `Multi-AZ - fr-par`, which hides the actual product context.

### Hourly Net Cost Evolution

Use this when you want one line for total net cost per hour.

```promql
(
  sum(increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[1h]))
  or vector(0)
)
-
(
  sum(increase(scaleway_billing_credit_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[1h]))
  or vector(0)
)
```

### Daily Cost Bars By Project

Use this for day-by-day bars. Set the panel minimum interval to `1d`.

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[1d])
) > 0
```

## Breakdown Panels

Use these for bar gauges, pie charts, tables, or stacked bars. They intentionally
preserve the label in `sum by (...)`. Remove labels only when you really want to
collapse that dimension.

### Cost By Project

```promql
sum by (project_name) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[$__range])
) > 0
```

### Cost By Category

```promql
sum by (category_name) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type=~"${billing_line_type:regex}",
    billing_usage_type=~"${billing_usage_type:regex}",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[$__range])
) > 0
```

### Cost By Product And Resource

```promql
sum by (
  project_name,
  category_name,
  product_name,
  resource_name,
  sku,
  unit,
  billing_usage_type,
  burn_rate_eligible
) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    billing_line_type="resource_usage",
    burn_rate_eligible=~"${burn_rate:raw}"
  }[$__range])
) > 0
```

### Cost By Billing Line Type

Use this to separate resource usage from commercial lines such as Gold support,
contracts, credits, and free-tier markers.

```promql
sum by (billing_line_type) (
  increase(scaleway_billing_cost_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}"
  }[$__range])
) > 0
```

## Runtime Burn-Rate Panels

Use burn-rate panels only for runtime resource usage. This excludes contracts,
subscriptions, storage capacity units, request/token usage, and free-tier markers.

```promql
sum by (
  project_name,
  category_name,
  product_name,
  resource_name
) (
  increase(scaleway_billing_resource_usage_euros_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}",
    burn_rate_eligible="true"
  }[1h])
) > 0
```

Set the panel unit to `EUR/hour` only for this query. Storage capacity costs, Gold
support, and contract lines are valid costs, but they should not be rendered as
runtime hourly burn.

## Quantity Panels

Use this for a table or bar chart of billed quantities. Always keep `unit` in the
grouping because quantities with different units cannot be added meaningfully.

```promql
sum by (project_name, product_name, sku, unit) (
  increase(scaleway_billing_billed_quantity_total{
    project_name=~"${project_name:regex}",
    category_name=~"${category_name:regex}",
    product_name=~"${product_name:regex}"
  }[$__range])
) > 0
```

## Tax Panels

Use this for an organization-level Stat panel.

```promql
(
  sum(increase(scaleway_billing_tax_euros_total[$__range]))
  or vector(0)
)
-
(
  sum(increase(scaleway_billing_tax_credit_euros_total[$__range]))
  or vector(0)
)
```

Scaleway tax rows are organization-level in the tested API. Treat project-level
tax-included values as estimates unless Scaleway exposes exact project-level
taxes.

## Dashboard JSON

Put exported Grafana dashboard JSON files in:

```text
dashboards/grafana/
```

Use a stable name such as `scaleway-billing-collector.json`.
