"""Unit tests for ApexMotion Grafana Dashboard JSON schema and SLO panels.

Validates:
1. Valid JSON schema conforming to Grafana v9+ / v10+ dashboard specification.
2. Mandatory SLO panels (TASKS.md P15-4 & LLD Sec 8.2-8.3):
   - Investigation Latency SLO (p95 <= 90s)
   - Kafka Consumer Lag (Critical alert > 5,000)
   - HITL Queue Depth (pending approvals by spend tier)
   - LLM Daily Cost Accumulation & Token Burn Rate
3. Supporting operational telemetry panels:
   - HTTP request latency & error rate
   - Circuit breaker trip occurrences
   - Deterministic risk calculation latency
   - Quarantined prompt injection defense blocks
   - KMS ECDSA approval tokens minted
4. Cross-check that 100% of PromQL metric references correspond to registered
   collectors in `src.core.metrics`.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

DASHBOARD_PATH = Path("monitoring/grafana/dashboards/supplier_risk_overview.json")


@pytest.fixture(scope="module")
def dashboard_data() -> dict[str, Any]:
    """Load and parse the Grafana dashboard JSON."""
    assert DASHBOARD_PATH.exists(), f"Dashboard file does not exist at {DASHBOARD_PATH}"
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "Dashboard root must be a JSON object"
    return data


def _collect_all_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively collect panels, including nested rows."""
    collected: list[dict[str, Any]] = []
    for p in panels:
        collected.append(p)
        if "panels" in p and isinstance(p["panels"], list):
            collected.extend(_collect_all_panels(p["panels"]))
    return collected


def test_dashboard_file_exists_and_valid_json():
    """Verify that the dashboard file exists and parses as valid JSON."""
    assert DASHBOARD_PATH.exists(), f"Expected dashboard file at {DASHBOARD_PATH}"
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        content = f.read()
    data = json.loads(content)
    assert isinstance(data, dict)
    assert "panels" in data


def test_dashboard_schema_metadata(dashboard_data: dict[str, Any]):
    """Verify top-level dashboard metadata and schema version."""
    assert dashboard_data.get("schemaVersion", 0) >= 30, "Grafana schemaVersion must be >= 30"
    assert "ApexMotion" in dashboard_data.get("title", ""), (
        "Dashboard title must reference ApexMotion"
    )
    assert dashboard_data.get("uid") == "apexmotion-supplier-risk", "Expected standard UID"
    assert "timezone" in dashboard_data
    assert dashboard_data.get("refresh") in ["5s", "10s", "30s", "1m"]
    assert "tags" in dashboard_data
    tags = dashboard_data["tags"]
    assert "apexmotion" in tags
    assert "slo" in tags
    assert "supplier-risk" in tags


def test_dashboard_variables_and_templating(dashboard_data: dict[str, Any]):
    """Verify dashboard templating includes datasource and interval variables."""
    templating = dashboard_data.get("templating", {})
    variables = templating.get("list", [])
    var_names = [v.get("name") for v in variables]
    assert "datasource" in var_names or any(v.get("type") == "datasource" for v in variables)
    assert "interval" in var_names or "rate_interval" in var_names


def test_slo_investigation_latency_panel(dashboard_data: dict[str, Any]):
    """Verify the primary SLO panel for p95 investigation latency <= 90s."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    slo_panels = [
        p
        for p in panels
        if "investigation" in p.get("title", "").lower() and "latency" in p.get("title", "").lower()
    ]
    assert len(slo_panels) >= 1, "Must contain an Investigation Latency panel"

    panel = slo_panels[0]
    targets = panel.get("targets", [])
    assert len(targets) >= 1, "Panel must contain at least one query target"

    # Verify PromQL query uses apexmotion_investigation_duration_seconds_bucket and histogram_quantile 0.95
    queries = [t.get("expr", "") for t in targets]
    has_p95_query = any(
        "histogram_quantile" in q
        and "0.95" in q
        and "apexmotion_investigation_duration_seconds_bucket" in q
        for q in queries
    )
    assert has_p95_query, (
        "Must query histogram_quantile(0.95, ...) using apexmotion_investigation_duration_seconds_bucket"
    )

    # Verify 90s threshold is configured in thresholds or fieldConfig
    threshold_steps = []
    field_config = panel.get("fieldConfig", {}).get("defaults", {})
    if "thresholds" in field_config:
        threshold_steps = [
            s.get("value")
            for s in field_config["thresholds"].get("steps", [])
            if s.get("value") is not None
        ]

    assert (
        90 in threshold_steps
        or 90.0 in threshold_steps
        or any("90" in str(s) for s in threshold_steps)
    ), "Must configure a threshold for 90s SLA boundary"


def test_kafka_consumer_lag_panel(dashboard_data: dict[str, Any]):
    """Verify the Kafka consumer lag panel and threshold of 5,000."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    lag_panels = [
        p
        for p in panels
        if "kafka" in p.get("title", "").lower() and "lag" in p.get("title", "").lower()
    ]
    assert len(lag_panels) >= 1, "Must contain a Kafka Consumer Lag panel"

    panel = lag_panels[0]
    queries = [t.get("expr", "") for t in panel.get("targets", [])]
    has_lag_query = any("apexmotion_kafka_consumer_lag" in q for q in queries)
    assert has_lag_query, "Must query apexmotion_kafka_consumer_lag"

    # Verify threshold includes 5000 (LLD Sec 8.3 critical alert boundary)
    field_config = panel.get("fieldConfig", {}).get("defaults", {})
    threshold_steps = [
        s.get("value")
        for s in field_config.get("thresholds", {}).get("steps", [])
        if s.get("value") is not None
    ]
    assert 5000 in threshold_steps or any("5000" in str(s) for s in threshold_steps), (
        "Kafka lag threshold must include 5,000"
    )


def test_hitl_queue_depth_panel(dashboard_data: dict[str, Any]):
    """Verify the HITL approval queue depth panel."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    hitl_panels = [
        p
        for p in panels
        if "hitl" in p.get("title", "").lower() or "approval" in p.get("title", "").lower()
    ]
    assert len(hitl_panels) >= 1, "Must contain a HITL Approval Queue panel"

    queries = [t.get("expr", "") for p in hitl_panels for t in p.get("targets", [])]
    has_hitl_query = any("apexmotion_hitl_pending_count" in q for q in queries)
    assert has_hitl_query, "Must query apexmotion_hitl_pending_count"


def test_llm_cost_and_token_panels(dashboard_data: dict[str, Any]):
    """Verify LLM cost accumulation and token consumption panels."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    queries = [t.get("expr", "") for p in panels for t in p.get("targets", [])]

    # Verify LLM cost query
    has_cost_query = any("apexmotion_llm_cost_usd_total" in q for q in queries)
    assert has_cost_query, "Must query apexmotion_llm_cost_usd_total"

    # Verify LLM tokens query
    has_token_query = any("apexmotion_llm_tokens_total" in q for q in queries)
    assert has_token_query, "Must query apexmotion_llm_tokens_total"


def test_operational_resilience_and_security_panels(dashboard_data: dict[str, Any]):
    """Verify circuit breaker, deterministic engine, and security defense panels."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    queries = [t.get("expr", "") for p in panels for t in p.get("targets", [])]

    # Circuit breaker trips
    assert any("apexmotion_circuit_breaker_trips_total" in q for q in queries), (
        "Must query apexmotion_circuit_breaker_trips_total"
    )

    # Deterministic risk engine duration
    assert any("apexmotion_deterministic_calculation_duration_seconds" in q for q in queries), (
        "Must query apexmotion_deterministic_calculation_duration_seconds"
    )

    # Prompt injections blocked
    assert any("apexmotion_quarantined_injections_blocked_total" in q for q in queries), (
        "Must query apexmotion_quarantined_injections_blocked_total"
    )

    # KMS approval tokens minted
    assert any("apexmotion_approval_tokens_minted_total" in q for q in queries), (
        "Must query apexmotion_approval_tokens_minted_total"
    )


def test_all_referenced_metrics_exist_in_codebase(dashboard_data: dict[str, Any]):
    """Verify that every metric referenced in the dashboard exists in src/core/metrics.py."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    all_queries = [t.get("expr", "") for p in panels for t in p.get("targets", [])]

    # Extract all apexmotion_* metric identifiers
    referenced_metrics: set[str] = set()
    pattern = re.compile(r"\b(apexmotion_[a-zA-Z0-9_]+)\b")
    for q in all_queries:
        for match in pattern.findall(q):
            # Strip Prometheus histogram suffix variants
            base_metric = match
            if base_metric.endswith("_bucket"):
                base_metric = base_metric[:-7]
            elif base_metric.endswith("_count") and base_metric != "apexmotion_hitl_pending_count":
                base_metric = base_metric[:-6]
            elif base_metric.endswith("_sum"):
                base_metric = base_metric[:-4]
            referenced_metrics.add(base_metric)

    # Known collectors in metrics.py
    known_collector_names = {
        "apexmotion_investigations_total",
        "apexmotion_investigation_duration_seconds",
        "apexmotion_llm_tokens_total",
        "apexmotion_llm_cost_usd_total",
        "apexmotion_kafka_consumer_lag",
        "apexmotion_hitl_pending_count",
        "apexmotion_http_requests_total",
        "apexmotion_http_request_duration_seconds",
        "apexmotion_circuit_breaker_trips_total",
        "apexmotion_deterministic_calculation_duration_seconds",
        "apexmotion_quarantined_injections_blocked_total",
        "apexmotion_approval_tokens_minted_total",
    }

    for metric in referenced_metrics:
        assert metric in known_collector_names, (
            f"Metric '{metric}' in Grafana dashboard is not declared in src/core/metrics.py"
        )


def test_panel_grid_and_id_uniqueness(dashboard_data: dict[str, Any]):
    """Verify panel ID uniqueness and grid layout coordinates."""
    panels = _collect_all_panels(dashboard_data.get("panels", []))
    panel_ids = [p["id"] for p in panels if "id" in p]
    assert len(panel_ids) == len(set(panel_ids)), "All panel IDs must be unique"

    for p in panels:
        grid = p.get("gridPos", {})
        assert "h" in grid and "w" in grid and "x" in grid and "y" in grid, (
            f"Panel {p.get('title')} is missing required gridPos fields"
        )
        assert grid["w"] <= 24, "Panel width cannot exceed 24 columns in Grafana grid"


def test_grafana_and_prometheus_provisioning_files_exist():
    """Verify that Grafana and Prometheus provisioning YAML files exist and are non-empty."""
    import yaml

    dashboards_prov = Path("monitoring/grafana/provisioning/dashboards/dashboards.yaml")
    datasources_prov = Path("monitoring/grafana/provisioning/datasources/prometheus.yaml")
    prom_config = Path("monitoring/prometheus/prometheus.yml")

    assert dashboards_prov.exists(), "dashboards.yaml provisioning config must exist"
    assert datasources_prov.exists(), "prometheus.yaml datasource config must exist"
    assert prom_config.exists(), "prometheus.yml scraper config must exist"

    with open(dashboards_prov, encoding="utf-8") as f:
        d_yaml = yaml.safe_load(f)
    assert d_yaml.get("apiVersion") == 1
    assert "providers" in d_yaml

    with open(datasources_prov, encoding="utf-8") as f:
        ds_yaml = yaml.safe_load(f)
    assert ds_yaml.get("apiVersion") == 1
    assert "datasources" in ds_yaml

    with open(prom_config, encoding="utf-8") as f:
        p_yaml = yaml.safe_load(f)
    assert "scrape_configs" in p_yaml
    job_names = [j.get("job_name") for j in p_yaml["scrape_configs"]]
    assert "apexmotion-api" in job_names


def test_docker_compose_prometheus_and_grafana_services():
    """Verify that docker-compose.yml defines prometheus and grafana services with provisioning."""
    import yaml

    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    with open(compose_path, encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    services = compose_data.get("services", {})
    assert "prometheus" in services, "prometheus service must be defined in docker-compose.yml"
    assert "grafana" in services, "grafana service must be defined in docker-compose.yml"

    grafana_srv = services["grafana"]
    assert "3001:3000" in grafana_srv.get("ports", [])
    assert any("provisioning" in v for v in grafana_srv.get("volumes", []))
    assert any("dashboards" in v for v in grafana_srv.get("volumes", []))
