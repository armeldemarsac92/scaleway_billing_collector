# Grafana PromQL

These queries assume Grafana queries Prometheus or Thanos.

## Net Cost Over Dashboard Range

```promql
sum(increase(scaleway_billing_cost_euros_total[$__range]))
-
sum(increase(scaleway_billing_credit_euros_total[$__range]))
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

