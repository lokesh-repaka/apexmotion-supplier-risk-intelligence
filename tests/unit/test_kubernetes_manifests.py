"""Unit test suite for Kubernetes manifests and KEDA autoscaling (P16-4).

Validates syntax, structure, security contexts, probes, autoscaling parameters,
and Kustomize bundling for production Amazon EKS 1.30 deployment.
Offline isolation: pure YAML validation without live Kubernetes cluster.
"""

from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = Path("infrastructure/kubernetes")

REQUIRED_MANIFESTS = [
    "namespace.yaml",
    "configmap.yaml",
    "secrets.yaml",
    "api-deployment.yaml",
    "api-service.yaml",
    "api-hpa.yaml",
    "worker-deployment.yaml",
    "worker-keda-scaledobject.yaml",
    "kustomization.yaml",
]


def load_yaml(file_path: Path) -> list[dict[str, Any]]:
    """Helper to safely load all YAML documents from a file."""
    assert file_path.exists(), f"Manifest file missing: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    return [doc for doc in docs if doc is not None]


def test_manifest_files_exist() -> None:
    """Verify that all required Kubernetes manifest files exist in infrastructure/kubernetes/."""
    for filename in REQUIRED_MANIFESTS:
        file_path = MANIFEST_DIR / filename
        assert file_path.exists(), f"Missing required Kubernetes manifest: {file_path}"


def test_all_yaml_manifests_valid() -> None:
    """Verify that every manifest file is valid syntax YAML and parses cleanly."""
    for filename in REQUIRED_MANIFESTS:
        docs = load_yaml(MANIFEST_DIR / filename)
        assert len(docs) >= 1, f"Empty YAML file: {filename}"


def test_namespace_specification() -> None:
    """Verify namespace manifest declares 'apexmotion' with proper governance labels."""
    docs = load_yaml(MANIFEST_DIR / "namespace.yaml")
    ns = docs[0]
    assert ns.get("apiVersion") == "v1"
    assert ns.get("kind") == "Namespace"
    metadata = ns.get("metadata", {})
    assert metadata.get("name") == "apexmotion"
    labels = metadata.get("labels", {})
    assert labels.get("app.kubernetes.io/name") == "apexmotion"
    assert labels.get("app.kubernetes.io/part-of") == "apexmotion-platform"


def test_configmap_specification() -> None:
    """Verify ConfigMap contains required operational configurations and MSK topics."""
    docs = load_yaml(MANIFEST_DIR / "configmap.yaml")
    cm = docs[0]
    assert cm.get("apiVersion") == "v1"
    assert cm.get("kind") == "ConfigMap"
    assert cm.get("metadata", {}).get("name") == "apexmotion-config"
    assert cm.get("metadata", {}).get("namespace") == "apexmotion"

    data = cm.get("data", {})
    assert "ENVIRONMENT" in data
    assert "AWS_REGION" in data
    assert "KAFKA_BOOTSTRAP_SERVERS" in data
    assert "KAFKA_TOPIC_SUPPLIER_EVENTS" in data
    assert "KAFKA_CONSUMER_GROUP" in data
    assert data.get("KAFKA_CONSUMER_GROUP") == "apexmotion-risk-engine"
    assert "PROMETHEUS_METRICS_ENABLED" in data
    assert data.get("PROMETHEUS_METRICS_ENABLED") == "true"


def test_secrets_specification() -> None:
    """Verify Secret manifest contains template keys for secure credentials."""
    docs = load_yaml(MANIFEST_DIR / "secrets.yaml")
    sec = docs[0]
    assert sec.get("apiVersion") == "v1"
    assert sec.get("kind") == "Secret"
    assert sec.get("metadata", {}).get("name") == "apexmotion-secrets"
    assert sec.get("metadata", {}).get("namespace") == "apexmotion"
    assert sec.get("type") in ("Opaque", "kubernetes.io/opaque")

    # Check that required keys are declared (either data or stringData)
    keys = set(sec.get("data", {}).keys()) | set(sec.get("stringData", {}).keys())
    assert "DATABASE_URL" in keys
    assert "KEYCLOAK_CLIENT_SECRET" in keys
    assert "LANGFUSE_SECRET_KEY" in keys


def test_api_deployment_specification() -> None:
    """Verify API Deployment adheres to CIS hardening, multi-AZ scheduling, and probes."""
    docs = load_yaml(MANIFEST_DIR / "api-deployment.yaml")
    deploy = docs[0]
    assert deploy.get("apiVersion") == "apps/v1"
    assert deploy.get("kind") == "Deployment"
    assert deploy.get("metadata", {}).get("name") == "apexmotion-api"
    assert deploy.get("metadata", {}).get("namespace") == "apexmotion"

    spec = deploy.get("spec", {})
    assert spec.get("replicas", 0) >= 3

    # Pod Template
    template = spec.get("template", {})
    pod_spec = template.get("spec", {})

    # Pod Anti-Affinity (Multi-AZ resilience)
    affinity = pod_spec.get("affinity", {})
    pod_anti_affinity = affinity.get("podAntiAffinity", {})
    assert (
        "preferredDuringSchedulingIgnoredDuringExecution" in pod_anti_affinity
        or "requiredDuringSchedulingIgnoredDuringExecution" in pod_anti_affinity
    )

    containers = pod_spec.get("containers", [])
    assert len(containers) >= 1
    api_container = containers[0]
    assert api_container.get("name") == "api"

    # Port
    ports = api_container.get("ports", [])
    assert any(p.get("containerPort") == 8000 for p in ports)

    # Health Probes
    liveness = api_container.get("livenessProbe", {})
    assert liveness.get("httpGet", {}).get("path") == "/health"
    assert liveness.get("httpGet", {}).get("port") == 8000

    readiness = api_container.get("readinessProbe", {})
    assert readiness.get("httpGet", {}).get("path") == "/health"
    assert readiness.get("httpGet", {}).get("port") == 8000

    # Security Context: Non-root UID 10001
    sec_ctx = api_container.get("securityContext", {})
    pod_sec_ctx = pod_spec.get("securityContext", {})
    run_as_non_root = sec_ctx.get("runAsNonRoot") or pod_sec_ctx.get("runAsNonRoot")
    assert run_as_non_root is True
    run_as_user = sec_ctx.get("runAsUser") or pod_sec_ctx.get("runAsUser")
    assert run_as_user == 10001
    run_as_group = sec_ctx.get("runAsGroup") or pod_sec_ctx.get("runAsGroup")
    assert run_as_group == 10001
    assert sec_ctx.get("allowPrivilegeEscalation") is False
    assert "ALL" in sec_ctx.get("capabilities", {}).get("drop", [])

    # Resources
    resources = api_container.get("resources", {})
    assert "requests" in resources
    assert "limits" in resources
    assert "cpu" in resources["requests"]
    assert "memory" in resources["requests"]


def test_api_service_specification() -> None:
    """Verify API Service declares ClusterIP, port 80 -> 8000, and Prometheus scraping annotations."""
    docs = load_yaml(MANIFEST_DIR / "api-service.yaml")
    svc = docs[0]
    assert svc.get("apiVersion") == "v1"
    assert svc.get("kind") == "Service"
    assert svc.get("metadata", {}).get("name") == "apexmotion-api"
    assert svc.get("metadata", {}).get("namespace") == "apexmotion"

    annotations = svc.get("metadata", {}).get("annotations", {})
    assert annotations.get("prometheus.io/scrape") == "true"
    assert annotations.get("prometheus.io/port") == "8000"
    assert annotations.get("prometheus.io/path") == "/metrics"

    spec = svc.get("spec", {})
    assert spec.get("type", "ClusterIP") == "ClusterIP"
    ports = spec.get("ports", [])
    assert any(p.get("port") == 80 and p.get("targetPort") == 8000 for p in ports)


def test_api_hpa_specification() -> None:
    """Verify HorizontalPodAutoscaler targets API deployment with 3-20 replicas and 70% CPU threshold."""
    docs = load_yaml(MANIFEST_DIR / "api-hpa.yaml")
    hpa = docs[0]
    assert hpa.get("apiVersion") == "autoscaling/v2"
    assert hpa.get("kind") == "HorizontalPodAutoscaler"
    assert hpa.get("metadata", {}).get("name") == "apexmotion-api-hpa"
    assert hpa.get("metadata", {}).get("namespace") == "apexmotion"

    spec = hpa.get("spec", {})
    target_ref = spec.get("scaleTargetRef", {})
    assert target_ref.get("kind") == "Deployment"
    assert target_ref.get("name") == "apexmotion-api"
    assert spec.get("minReplicas") == 3
    assert spec.get("maxReplicas") == 20

    metrics = spec.get("metrics", [])
    cpu_metric = next((m for m in metrics if m.get("resource", {}).get("name") == "cpu"), None)
    assert cpu_metric is not None
    assert cpu_metric.get("resource", {}).get("target", {}).get("averageUtilization") == 70


def test_worker_deployment_specification() -> None:
    """Verify Worker Deployment initializes 4 replicas, runs Kafka consumer, and enforces non-root UID 10001."""
    docs = load_yaml(MANIFEST_DIR / "worker-deployment.yaml")
    deploy = docs[0]
    assert deploy.get("apiVersion") == "apps/v1"
    assert deploy.get("kind") == "Deployment"
    assert deploy.get("metadata", {}).get("name") == "apexmotion-worker"
    assert deploy.get("metadata", {}).get("namespace") == "apexmotion"

    spec = deploy.get("spec", {})
    assert spec.get("replicas") == 4

    pod_spec = spec.get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    assert len(containers) >= 1
    worker_container = containers[0]
    assert worker_container.get("name") == "worker"

    # Security Context: Non-root UID 10001
    sec_ctx = worker_container.get("securityContext", {})
    pod_sec_ctx = pod_spec.get("securityContext", {})
    run_as_non_root = sec_ctx.get("runAsNonRoot") or pod_sec_ctx.get("runAsNonRoot")
    assert run_as_non_root is True
    run_as_user = sec_ctx.get("runAsUser") or pod_sec_ctx.get("runAsUser")
    assert run_as_user == 10001
    assert sec_ctx.get("allowPrivilegeEscalation") is False
    assert "ALL" in sec_ctx.get("capabilities", {}).get("drop", [])

    # Resources
    resources = worker_container.get("resources", {})
    assert "requests" in resources
    assert "limits" in resources


def test_worker_keda_scaledobject_specification() -> None:
    """Verify KEDA ScaledObject scales worker pods from 4 to 32 based on consumer group lag > 5000."""
    docs = load_yaml(MANIFEST_DIR / "worker-keda-scaledobject.yaml")
    scaled_obj = docs[0]
    assert scaled_obj.get("apiVersion") == "keda.sh/v1alpha1"
    assert scaled_obj.get("kind") == "ScaledObject"
    assert scaled_obj.get("metadata", {}).get("name") == "apexmotion-worker-keda"
    assert scaled_obj.get("metadata", {}).get("namespace") == "apexmotion"

    spec = scaled_obj.get("spec", {})
    target_ref = spec.get("scaleTargetRef", {})
    assert target_ref.get("name") == "apexmotion-worker"
    assert spec.get("minReplicaCount") == 4
    assert spec.get("maxReplicaCount") == 32
    assert spec.get("cooldownPeriod", 0) >= 300

    triggers = spec.get("triggers", [])
    assert len(triggers) >= 1
    kafka_trigger = triggers[0]
    assert kafka_trigger.get("type") == "kafka"

    metadata = kafka_trigger.get("metadata", {})
    assert "apexmotion-risk-engine" in metadata.get("consumerGroup", "")
    assert metadata.get("topic") == "supplier-events"
    assert str(metadata.get("lagThreshold")) == "5000"
    assert str(metadata.get("activationLagThreshold")) == "1000"


def test_kustomization_specification() -> None:
    """Verify Kustomization bundles all manifests into a clean deployment package."""
    docs = load_yaml(MANIFEST_DIR / "kustomization.yaml")
    kust = docs[0]
    assert kust.get("apiVersion") == "kustomize.config.k8s.io/v1beta1"
    assert kust.get("kind") == "Kustomization"
    assert kust.get("namespace") == "apexmotion"

    resources = kust.get("resources", [])
    expected_resources = [m for m in REQUIRED_MANIFESTS if m != "kustomization.yaml"]
    for r in expected_resources:
        assert r in resources, f"Missing resource '{r}' in kustomization.yaml"
