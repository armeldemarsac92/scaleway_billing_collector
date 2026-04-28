# Scaleway Billing Collector

Python service that snapshots Scaleway Billing API usage, computes daily deltas per project/component, and exposes Prometheus metrics for Thanos/Grafana.

See [BILLING_COLLECTOR_PLAN.md](BILLING_COLLECTOR_PLAN.md) for the implementation plan.

Operational docs:

- [Kubernetes deployment](deploy/kubernetes/README.md)
- [Runbook](docs/runbook.md)
- [Grafana PromQL](docs/grafana-promql.md)
