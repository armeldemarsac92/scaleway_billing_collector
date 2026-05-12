{{/*
Expand the chart name.
*/}}
{{- define "scaleway-billing-collector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "scaleway-billing-collector.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "scaleway-billing-collector.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{ include "scaleway-billing-collector.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{/*
Selector labels.
*/}}
{{- define "scaleway-billing-collector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "scaleway-billing-collector.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{/*
Secret name. Used both for created and pre-existing secrets.
*/}}
{{- define "scaleway-billing-collector.secretName" -}}
{{- default (include "scaleway-billing-collector.fullname" .) .Values.secret.name -}}
{{- end -}}

{{/*
PVC name.
*/}}
{{- define "scaleway-billing-collector.pvcName" -}}
{{- default (printf "%s-data" (include "scaleway-billing-collector.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}
