{{/* Trimmed from `helm create`'s own scaffold — just the name/label helpers a two-template chart
actually uses. */}}

{{- define "sample-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "sample-service.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "sample-service.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "sample-service.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "sample-service.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "sample-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sample-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
