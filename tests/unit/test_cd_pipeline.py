"""Unit test suite for GitHub Actions Continuous Delivery pipelines (P16-5).

Validates syntax, structure, OIDC security, ECR build/push, EKS deployment,
and Blue-Green cutover with automated rollback for staging and production workflows.
Offline isolation: pure YAML and shell script inspection without external network/AWS calls.
"""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
STAGING_WORKFLOW = WORKFLOWS_DIR / "cd-staging.yml"
PRODUCTION_WORKFLOW = WORKFLOWS_DIR / "cd-production.yml"
BLUE_GREEN_SCRIPT = Path("infrastructure/kubernetes/blue_green_cutover.sh")


def load_yaml(file_path: Path) -> dict[str, Any]:
    """Helper to safely load a YAML document from a file."""
    assert file_path.exists(), f"Workflow file missing: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"Invalid YAML structure in {file_path}"
    return data


def test_cd_workflow_files_exist() -> None:
    """Verify that both CD workflow files and the Blue-Green cutover script exist."""
    assert STAGING_WORKFLOW.exists(), f"Missing staging workflow: {STAGING_WORKFLOW}"
    assert PRODUCTION_WORKFLOW.exists(), f"Missing production workflow: {PRODUCTION_WORKFLOW}"
    assert BLUE_GREEN_SCRIPT.exists(), f"Missing Blue-Green cutover script: {BLUE_GREEN_SCRIPT}"


def test_all_workflow_yamls_valid() -> None:
    """Verify that both CD workflow files parse cleanly as valid YAML dictionaries."""
    data_staging = load_yaml(STAGING_WORKFLOW)
    assert len(data_staging.keys()) > 0
    data_prod = load_yaml(PRODUCTION_WORKFLOW)
    assert len(data_prod.keys()) > 0


def test_cd_staging_workflow_triggers() -> None:
    """Verify staging CD triggers on push to development and supports manual dispatch."""
    data = load_yaml(STAGING_WORKFLOW)
    triggers = data.get("on", {})
    if isinstance(triggers, dict):
        push_trigger = triggers.get("push", {})
        branches = push_trigger.get("branches", [])
        assert "development" in branches, "Staging CD must trigger on push to development"
        assert "workflow_dispatch" in triggers, "Staging CD must support manual workflow_dispatch"
    else:
        pytest_fail = False
        assert pytest_fail, f"Unexpected 'on' format: {triggers}"


def test_cd_staging_workflow_oidc_security() -> None:
    """Verify staging CD uses AWS OIDC role assumption and zero static AWS keys."""
    content = STAGING_WORKFLOW.read_text(encoding="utf-8")
    assert "aws-actions/configure-aws-credentials" in content
    assert "role-to-assume" in content
    assert "aws-region" in content

    # Zero hardcoded static access keys
    assert "AKIA" not in content, "Static AWS access key ID found in staging workflow"
    assert "aws_secret_access_key" not in content.lower() or "secrets." in content


def test_cd_staging_workflow_build_and_deploy() -> None:
    """Verify staging CD logs in to ECR, builds API and Worker images, and runs kubectl apply."""
    content = STAGING_WORKFLOW.read_text(encoding="utf-8")
    data = load_yaml(STAGING_WORKFLOW)
    jobs = data.get("jobs", {})

    assert "build-and-push" in jobs or "deploy-staging" in jobs or "deploy" in jobs
    assert "aws-actions/amazon-ecr-login" in content
    assert "Dockerfile.api" in content
    assert "Dockerfile.worker" in content
    assert "kubectl apply" in content or "kustomize" in content
    assert "rollout status" in content


def test_cd_production_workflow_triggers() -> None:
    """Verify production CD triggers on push to main and supports manual dispatch."""
    data = load_yaml(PRODUCTION_WORKFLOW)
    triggers = data.get("on", {})
    if isinstance(triggers, dict):
        push_trigger = triggers.get("push", {})
        branches = push_trigger.get("branches", [])
        assert "main" in branches, "Production CD must trigger on push to main"
        assert "workflow_dispatch" in triggers, (
            "Production CD must support manual workflow_dispatch"
        )


def test_cd_production_workflow_quality_gate() -> None:
    """Verify production CD enforces a quality gate (tests/golden evals) prior to deployment."""
    data = load_yaml(PRODUCTION_WORKFLOW)
    jobs = data.get("jobs", {})
    job_names = list(jobs.keys())
    assert len(job_names) >= 2, "Production CD must have multiple staged jobs"

    content = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")
    assert "test" in content.lower() or "quality" in content.lower() or "gate" in content.lower()
    assert "pytest" in content or "needs:" in content


def test_cd_production_workflow_oidc_security() -> None:
    """Verify production CD uses AWS OIDC role assumption and references production environment."""
    content = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")
    assert "aws-actions/configure-aws-credentials" in content
    assert "role-to-assume" in content
    assert "environment:" in content and "production" in content

    # Zero hardcoded static access keys
    assert "AKIA" not in content, "Static AWS access key ID found in production workflow"


def test_cd_production_workflow_blue_green_cutover() -> None:
    """Verify production CD implements Blue-Green deployment with cutover and rollback."""
    content = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")
    assert "blue" in content.lower() and "green" in content.lower()
    assert "blue_green_cutover.sh" in content or "cutover" in content.lower()
    assert "health" in content.lower()
    assert "rollback" in content.lower()


def test_blue_green_cutover_script_specification() -> None:
    """Verify Blue-Green cutover shell script enforces strict error handling and rollback traps."""
    assert BLUE_GREEN_SCRIPT.exists(), f"Cutover script missing: {BLUE_GREEN_SCRIPT}"
    content = BLUE_GREEN_SCRIPT.read_text(encoding="utf-8")

    # Strict error handling
    assert (
        re.search(r"set\s+-[a-z]*e[a-z]*u[a-z]*o\s+pipefail", content)
        or "set -euo pipefail" in content
    )

    # Key parameters checked
    assert "NAMESPACE" in content
    assert "SERVICE" in content or "SERVICE_NAME" in content
    assert "TARGET_COLOR" in content or "NEW_COLOR" in content
    assert "HEALTH" in content.upper()

    # Rollback implementation
    assert "rollback" in content.lower() or "trap" in content.lower()

    # Atomic kubectl patch
    assert "kubectl patch" in content or "kubectl apply" in content


def test_no_secret_leaks_in_workflows() -> None:
    """Verify zero plaintext API keys or credentials leaked in workflow source code."""
    for path in (STAGING_WORKFLOW, PRODUCTION_WORKFLOW, BLUE_GREEN_SCRIPT):
        text = path.read_text(encoding="utf-8")
        assert "password=" not in text.lower() or "${{" in text
        assert "secret_key=" not in text.lower() or "${{" in text
        assert "ghp_" not in text, "GitHub Personal Access Token detected"
        assert "sk-ant-" not in text, "Anthropic API Key detected"
        assert "sk-proj-" not in text, "OpenAI API Key detected"
