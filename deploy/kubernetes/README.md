# Kubernetes Deployment

The manifests deploy one collector pod in the `monitoring` namespace, backed by a SQLite PVC and scraped by `kube-prometheus-stack` through a `ServiceMonitor`.

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

