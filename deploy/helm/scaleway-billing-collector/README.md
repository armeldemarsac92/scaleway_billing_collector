# Scaleway Billing Collector Helm Chart

This chart deploys the collector as one Kubernetes `Deployment`, backed by a SQLite `PersistentVolumeClaim`, exposed through a `Service`, and scraped through a Prometheus Operator `ServiceMonitor`.

The collector is Prometheus-first. It starts collecting from deployment time onward and does not backfill older months.

## Install

Create the Scaleway Secret first:

```bash
kubectl -n monitoring create secret generic scaleway-billing-collector \
  --from-literal=SCW_SECRET_KEY='<scaleway-secret-key>' \
  --from-literal=SCW_ORGANIZATION_ID='<organization-id>'
```

Install or upgrade:

```bash
helm upgrade --install scaleway-billing-collector deploy/helm/scaleway-billing-collector \
  --namespace monitoring \
  --create-namespace
```

Install from the published OCI chart:

```bash
helm upgrade --install scaleway-billing-collector \
  oci://ghcr.io/armeldemarsac92/charts/scaleway-billing-collector \
  --namespace monitoring \
  --create-namespace
```

The default release name matches the default Secret name. If you use another release name or Secret name, set:

```bash
helm upgrade --install my-billing-collector deploy/helm/scaleway-billing-collector \
  --namespace monitoring \
  --create-namespace \
  --set secret.name=scaleway-billing-collector
```

You can also let Helm create the Secret:

```bash
helm upgrade --install scaleway-billing-collector deploy/helm/scaleway-billing-collector \
  --namespace monitoring \
  --create-namespace \
  --set secret.create=true \
  --set secret.scwSecretKey='<scaleway-secret-key>' \
  --set secret.scwOrganizationId='<organization-id>'
```

## Published Artifacts

The GitHub Actions workflow publishes:

- Docker image: `ghcr.io/armeldemarsac92/scaleway_billing_collector`
- Helm chart: `oci://ghcr.io/armeldemarsac92/charts/scaleway-billing-collector`
- packaged chart `.tgz` as a workflow artifact

On `main`, the Docker image gets `latest` and `sha-*` tags. The chart version is generated as `<Chart.yaml version>-<run number>.<run attempt>`, for example `0.1.0-42.1`.

On version tags such as `v0.1.0`, the Docker image and Helm chart use the tag version.

## Prometheus

`serviceMonitor.enabled` is `true` by default. The chart adds this label to the `ServiceMonitor`:

```yaml
release: kube-prometheus-stack
```

If your Prometheus Operator uses another selector, override `serviceMonitor.labels`.

## Persistence

SQLite is stored on a PVC mounted at `/data`.

Defaults:

```yaml
persistence:
  enabled: true
  accessModes:
    - ReadWriteOnce
  size: 1Gi
```

Keep `replicaCount: 1`. SQLite is single-writer, and the chart uses a `Recreate` deployment strategy so upgrades do not briefly run two pods against the same PVC.

## Values

Common overrides:

```yaml
image:
  repository: ghcr.io/armeldemarsac92/scaleway_billing_collector
  tag: latest

config:
  projectIds: ""
  categoryNames: ""
  collectionIntervalSeconds: 3600
  previousPeriodBackfillDays: 7

serviceMonitor:
  labels:
    release: kube-prometheus-stack
```
