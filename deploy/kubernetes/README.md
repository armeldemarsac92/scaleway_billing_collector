# Kubernetes Deployment

The preferred deployment path is the Helm chart in [../helm/scaleway-billing-collector](../helm/scaleway-billing-collector).

These plain manifests remain available as a fallback. They deploy one collector pod in the `monitoring` namespace, backed by a SQLite PVC and scraped by `kube-prometheus-stack` through a `ServiceMonitor`.

The collector is Prometheus-first: it starts collecting live month-to-date snapshots when the pod starts, stores daily deltas in SQLite, and exposes cumulative counters from those live deltas. It does not backfill older months.

Create the Scaleway secret before applying the manifests:

```bash
kubectl -n monitoring create secret generic scaleway-billing-collector \
  --from-literal=SCW_SECRET_KEY='<scaleway-secret-key>' \
  --from-literal=SCW_ORGANIZATION_ID='<organization-id>'
```

Then apply:

```bash
kubectl apply -f deploy/kubernetes/scaleway-billing-collector.yaml
```

The API key should be read-only for billing consumption and project listing.
