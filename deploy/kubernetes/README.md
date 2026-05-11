# Kubernetes Deployment

The manifests deploy one collector pod in the `monitoring` namespace, backed by a SQLite PVC and scraped by `kube-prometheus-stack` through a `ServiceMonitor`.

An init container runs `billing-collector-seed-history` before the collector starts. It
backfills closed historical billing months once, marks the SQLite database after a
successful seed, and skips later pod starts unless the command is run manually with
`--force`.

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
