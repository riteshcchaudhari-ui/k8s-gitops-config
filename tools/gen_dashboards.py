#!/usr/bin/env python3
"""Grafana dashboards ko code se banata hai aur ConfigMap YAML me likhta hai.
Run: python3 tools/gen_dashboards.py   (output: platform/dashboards/)"""
import json
import pathlib

DS = {"type": "prometheus", "uid": "${datasource}"}
OUT = pathlib.Path(__file__).resolve().parent.parent / "platform" / "dashboards"


def panel(pid, title, exprs, x, y, w=12, h=8, unit="short", kind="timeseries"):
    targets = []
    for i, (expr, legend) in enumerate(exprs):
        targets.append({"refId": chr(65 + i), "expr": expr,
                        "legendFormat": legend, "datasource": DS})
    return {"id": pid, "title": title, "type": kind, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
            "targets": targets}


def dashboard(uid, title, panels, variables):
    return {"uid": uid, "title": title, "schemaVersion": 39, "version": 1,
            "editable": True, "refresh": "30s", "tags": ["capstone"],
            "time": {"from": "now-1h", "to": "now"},
            "panels": panels, "templating": {"list": variables}}


def configmap(name, dash):
    body = json.dumps(dash, indent=2)
    indented = "\n".join("    " + line for line in body.splitlines())
    return ("apiVersion: v1\nkind: ConfigMap\nmetadata:\n"
            "  name: " + name + "\n  namespace: monitoring\n"
            "  labels:\n    grafana_dashboard: \"1\"\n"
            "data:\n  " + name + ".json: |\n" + indented + "\n")


DS_VAR = {"name": "datasource", "type": "datasource",
          "query": "prometheus", "label": "Data source"}
NS_VAR = {"name": "namespace", "type": "custom", "label": "Environment",
          "query": "staging,production", "options": [],
          "current": {"text": "staging", "value": "staging"}}

# ---------- Dashboard 1: Cluster overview ----------
cluster = [
    panel(1, "Nodes Ready",
          [('sum(kube_node_status_condition{condition="Ready",status="true"})', "")],
          0, 0, 6, 4, kind="stat"),
    panel(2, "Running pods",
          [('sum(kube_pod_status_phase{phase="Running"})', "")],
          6, 0, 6, 4, kind="stat"),
    panel(3, "Pods not running",
          [('sum(kube_pod_status_phase{phase=~"Pending|Failed|Unknown"}) or vector(0)', "")],
          12, 0, 6, 4, kind="stat"),
    panel(4, "Pod restarts (last 1h)",
          [('sum(increase(kube_pod_container_status_restarts_total[1h]))', "")],
          18, 0, 6, 4, kind="stat"),
    panel(5, "Node CPU usage",
          [('100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100',
            "{{instance}}")], 0, 4, unit="percent"),
    panel(6, "Node memory usage",
          [('100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)',
            "{{instance}}")], 12, 4, unit="percent"),
    panel(7, "Running pods per namespace",
          [('sum by (namespace) (kube_pod_status_phase{phase="Running"})',
            "{{namespace}}")], 0, 12),
    panel(8, "Top restarting pods (1h)",
          [('topk(5, sum by (namespace, pod) (increase(kube_pod_container_status_restarts_total[1h])))',
            "{{namespace}}/{{pod}}")], 12, 12),
    panel(9, "CPU by namespace (cores)",
          [('sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",container!="POD"}[2m]))',
            "{{namespace}}")], 0, 20),
    panel(10, "Memory by namespace",
          [('sum by (namespace) (container_memory_working_set_bytes{container!=""})',
            "{{namespace}}")], 12, 20, unit="bytes"),
]

# ---------- Dashboard 2: Per-service health ----------
SVC = 'exported_service="${namespace}-easyshop-web-http@kubernetes"'
PODS = 'namespace="${namespace}", pod=~"(easyshop-web|mongodb)-.*"'
HPA = 'namespace="${namespace}", horizontalpodautoscaler="easyshop-web"'
REQ = 'traefik_service_requests_total{' + SVC
ERR_RATIO = ('100 * (sum(rate(' + REQ + ', code=~"5.."}[2m])) or vector(0))'
             ' / sum(rate(' + REQ + '}[2m]))')

service = [
    panel(1, "Request rate",
          [('sum(rate(' + REQ + '}[2m]))', "")], 0, 0, 6, 4, unit="reqps", kind="stat"),
    panel(2, "Error rate (5xx %)",
          [(ERR_RATIO, "")], 6, 0, 6, 4, unit="percent", kind="stat"),
    panel(3, "easyshop-web replicas",
          [('kube_horizontalpodautoscaler_status_current_replicas{' + HPA + '}', "")],
          12, 0, 6, 4, kind="stat"),
    panel(4, "Pod restarts (total)",
          [('sum(kube_pod_container_status_restarts_total{' + PODS + '})', "")],
          18, 0, 6, 4, kind="stat"),
    panel(5, "Request rate by status code",
          [('sum by (code) (rate(' + REQ + '}[2m]))', "{{code}}")],
          0, 4, unit="reqps"),
    panel(6, "Latency p95",
          [('histogram_quantile(0.95, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{'
            + SVC + '}[2m])))', "p95")], 12, 4, unit="s"),
    panel(7, "CPU per pod (cores)",
          [('sum by (pod) (rate(container_cpu_usage_seconds_total{' + PODS
            + ', container!="", container!="POD"}[2m]))', "{{pod}}")], 0, 12),
    panel(8, "Memory per pod",
          [('sum by (pod) (container_memory_working_set_bytes{' + PODS
            + ', container!=""})', "{{pod}}")], 12, 12, unit="bytes"),
    panel(9, "HPA replicas (autoscaling)",
          [('kube_horizontalpodautoscaler_status_current_replicas{' + HPA + '}', "current"),
           ('kube_horizontalpodautoscaler_status_desired_replicas{' + HPA + '}', "desired"),
           ('kube_horizontalpodautoscaler_spec_max_replicas{' + HPA + '}', "max")],
          0, 20),
    panel(10, "Pod restarts per pod",
          [('sum by (pod) (kube_pod_container_status_restarts_total{' + PODS + '})',
            "{{pod}}")], 12, 20),
]

OUT.mkdir(parents=True, exist_ok=True)
for name, dash in [
    ("dashboard-cluster-overview",
     dashboard("capstone-cluster", "Capstone: Cluster Overview", cluster, [DS_VAR])),
    ("dashboard-service-health",
     dashboard("capstone-service", "Capstone: Service Health", service, [DS_VAR, NS_VAR])),
]:
    (OUT / (name + ".yaml")).write_text(configmap(name, dash))
    print("wrote", name)
