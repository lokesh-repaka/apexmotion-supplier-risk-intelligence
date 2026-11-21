"""Unit tests for docker-compose.yml local development environment.

Verifies:
- docker-compose.yml exists and parses as valid YAML
- Defines required local infrastructure services: postgres, redis, redpanda, localstack, langfuse
- Port bindings match .env.example (5432, 6379, 9092, 4566, 3000)
- Health checks are configured for database and message broker services
- Volumes and networks are configured for container persistence and discovery
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent


def test_docker_compose_file_exists_and_valid_yaml():
    """Verify docker-compose.yml exists at root and parses as valid YAML."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"

    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert "services" in data


def test_docker_compose_defines_required_services():
    """Verify all five mandatory services are declared in docker-compose.yml."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    required = ["postgres", "redis", "redpanda", "localstack", "langfuse"]

    for req in required:
        assert req in services, f"Service '{req}' missing from docker-compose.yml"


def test_docker_compose_port_mappings():
    """Verify service port mappings match .env.example specifications."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})

    expected_ports = {
        "postgres": "5432",
        "redis": "6379",
        "redpanda": "9092",
        "localstack": "4566",
        "langfuse": "3000",
    }

    for svc_name, port_str in expected_ports.items():
        svc = services.get(svc_name, {})
        ports = [str(p) for p in svc.get("ports", [])]
        assert any(port_str in p for p in ports), (
            f"Port '{port_str}' not mapped for service '{svc_name}'. Found: {ports}"
        )


def test_docker_compose_postgres_credentials_match_env_example():
    """Verify PostgreSQL service environment matches .env.example DATABASE_URL configuration."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pg_env = data["services"]["postgres"]["environment"]
    # Handle dict or list format
    if isinstance(pg_env, list):
        pg_env = dict(item.split("=", 1) for item in pg_env)

    assert pg_env.get("POSTGRES_DB") == "apexmotion"
    assert pg_env.get("POSTGRES_USER") == "apexmotion_app"
    assert pg_env.get("POSTGRES_PASSWORD") == "local_dev_password"


def test_docker_compose_healthchecks_and_volumes():
    """Verify healthchecks exist on critical dependencies and persistent volumes are declared."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "healthcheck" in services["postgres"]
    assert "healthcheck" in services["redis"]
    assert "healthcheck" in services["redpanda"]

    volumes = data.get("volumes", {})
    assert "postgres_data" in volumes
    assert "redis_data" in volumes
    assert "redpanda_data" in volumes
