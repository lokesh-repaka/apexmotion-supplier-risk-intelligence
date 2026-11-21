"""Unit test verifying P1-1: Project Structure, pyproject.toml, frontend/package.json, and .env.example."""

import json
import tomllib
from pathlib import Path


def test_core_directory_skeleton_exists():
    """Verify that all architectural directories defined in CLAUDE.md Section 7 exist."""
    root = Path(__file__).parent.parent.parent

    required_src_dirs = [
        root / "src" / "api" / "routes",
        root / "src" / "api" / "schemas",
        root / "src" / "agents" / "nodes",
        root / "src" / "agents" / "tools",
        root / "src" / "services" / "risk",
        root / "src" / "llm" / "prompts",
        root / "src" / "graph" / "queries",
        root / "src" / "database" / "repositories",
        root / "src" / "database" / "migrations",
        root / "src" / "guardrails",
        root / "src" / "core",
        root / "src" / "kafka" / "schemas",
    ]

    for dir_path in required_src_dirs:
        assert dir_path.is_dir(), f"Missing required source directory: {dir_path}"
        init_file = (
            dir_path
            if dir_path.name != "routes" and dir_path.name != "schemas"
            else dir_path.parent
        )
        assert (dir_path / "__init__.py").exists() or (init_file / "__init__.py").exists(), (
            f"Missing __init__.py in package: {dir_path}"
        )


def test_pyproject_toml_configuration():
    """Verify pyproject.toml exists and declares correct dependencies and Python 3.12+."""
    root = Path(__file__).parent.parent.parent
    pyproject_path = root / "pyproject.toml"

    assert pyproject_path.exists(), "pyproject.toml does not exist"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    assert project.get("name") == "apexmotion-risk-platform"
    assert "3.12" in project.get("requires-python", "")

    deps = project.get("dependencies", [])
    dep_names = [d.split(">=")[0].split("==")[0].split("[")[0].strip().lower() for d in deps]

    expected_deps = [
        "fastapi",
        "pydantic",
        "pydantic-settings",
        "uvicorn",
        "langgraph",
        "sqlalchemy",
        "asyncpg",
        "redis",
        "litellm",
        "boto3",
        "cryptography",
    ]
    for dep in expected_deps:
        assert dep in dep_names, f"Expected dependency '{dep}' missing in pyproject.toml"


def test_frontend_package_json():
    """Verify frontend/package.json exists with React 18, Vite, and required scripts."""
    root = Path(__file__).parent.parent.parent
    package_json_path = root / "frontend" / "package.json"

    assert package_json_path.exists(), "frontend/package.json does not exist"

    with open(package_json_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("name") == "apexmotion-risk-frontend"
    scripts = data.get("scripts", {})
    for script_name in ["dev", "build", "lint", "type-check"]:
        assert script_name in scripts, f"Missing script '{script_name}' in frontend/package.json"

    dependencies = data.get("dependencies", {})
    for dep in ["react", "react-dom", "zustand", "lucide-react"]:
        assert dep in dependencies, f"Missing frontend dependency: {dep}"


def test_env_example_completeness():
    """Verify .env.example defines all required configuration variables from CLAUDE.md."""
    root = Path(__file__).parent.parent.parent
    env_example_path = root / ".env.example"

    assert env_example_path.exists(), ".env.example does not exist"

    content = env_example_path.read_text(encoding="utf-8")
    required_keys = [
        "AWS_REGION",
        "DATABASE_URL",
        "NEPTUNE_ENDPOINT",
        "OPENSEARCH_ENDPOINT",
        "REDIS_URL",
        "KAFKA_BOOTSTRAP_SERVERS",
        "LITELLM_BASE_URL",
        "KEYCLOAK_URL",
        "KMS_KEY_ARN",
        "LANGFUSE_PUBLIC_KEY",
        "HITL_TIER_1_THRESHOLD_USD",
        "HITL_TIER_2_THRESHOLD_USD",
        "USE_LOCALSTACK",
        "USE_MOCK_LLM",
        "USE_LOCAL_KAFKA",
    ]
    for key in required_keys:
        assert f"{key}=" in content, f"Key '{key}' missing in .env.example"


def test_nanocore_golden_scenario_exists():
    """Verify golden dataset tests/golden/nanocore_scenario.json exists with canonical metrics."""
    root = Path(__file__).parent.parent.parent
    golden_path = root / "tests" / "golden" / "nanocore_scenario.json"

    assert golden_path.exists(), "tests/golden/nanocore_scenario.json does not exist"

    with open(golden_path, encoding="utf-8") as f:
        scenario = json.load(f)

    inputs = scenario.get("inputs", {})
    assert inputs.get("current_stock") == 142000
    assert inputs.get("daily_consumption_rate") == 18500
    assert inputs.get("eta_days") == 9.0

    expected = scenario.get("expected", {})
    assert expected.get("days_of_cover") == 7.68
    assert expected.get("gap_days") == 1.32
    assert expected.get("shortage_volume") == 24420
    assert expected.get("financial_exposure_usd") == 2448105.00
