"""Unit tests for GitHub Actions CI pipeline and Docker configurations.

Verifies:
- .github/workflows/ci.yml exists and is valid YAML
- Triggers on push and PR to main and development branches
- Job stages: lint (ruff), type-check (mypy), test (pytest + coverage), docker-build
- Dockerfile.api and Dockerfile.worker exist, use non-root users, and proper entrypoints
- .dockerignore exists and ignores sensitive directories
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent


def test_ci_workflow_file_exists_and_valid_yaml():
    """Verify .github/workflows/ci.yml exists and parses as valid YAML."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), f"CI workflow file not found at {ci_path}"

    with open(ci_path, encoding="utf-8") as f:
        workflow_data = yaml.safe_load(f)

    assert isinstance(workflow_data, dict)
    assert "name" in workflow_data


def test_ci_triggers_on_main_and_development():
    """Verify CI workflow triggers on push and pull_request to development and main branches."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Workflow triggers (handling YAML boolean 'on' or string 'on')
    triggers = data.get("on") or data.get(True) or {}
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "development" in triggers["push"]["branches"]
    assert "main" in triggers["push"]["branches"]
    assert "development" in triggers["pull_request"]["branches"]
    assert "main" in triggers["pull_request"]["branches"]


def test_ci_defines_all_required_jobs():
    """Verify CI defines lint, type-check, test, and docker-build jobs."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    jobs = data.get("jobs", {})
    job_names = list(jobs.keys())

    # Verify key steps exist across jobs
    job_str = str(jobs).lower()
    assert any("lint" in name for name in job_names)
    assert any("type" in name or "mypy" in name for name in job_names)
    assert any("test" in name for name in job_names)
    assert any("docker" in name or "build" in name for name in job_names)

    # Verify ruff, mypy, pytest are invoked
    assert "ruff check" in job_str
    assert "mypy" in job_str
    assert "pytest" in job_str


def test_dockerfile_api_structure():
    """Verify Dockerfile.api exists, uses Python 3.12+, creates non-root user, and exposes port 8000."""
    dockerfile_path = REPO_ROOT / "Dockerfile.api"
    assert dockerfile_path.exists(), f"Dockerfile.api not found at {dockerfile_path}"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.12" in content
    assert "useradd" in content or "adduser" in content
    assert "USER " in content
    assert "EXPOSE 8000" in content
    assert "uvicorn" in content


def test_dockerfile_worker_structure():
    """Verify Dockerfile.worker exists, uses Python 3.12+, and creates non-root user."""
    dockerfile_path = REPO_ROOT / "Dockerfile.worker"
    assert dockerfile_path.exists(), f"Dockerfile.worker not found at {dockerfile_path}"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.12" in content
    assert "useradd" in content or "adduser" in content
    assert "USER " in content


def test_dockerignore_structure():
    """Verify .dockerignore exists and excludes secrets, virtualenvs, and test caches."""
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), f".dockerignore not found at {dockerignore_path}"

    content = dockerignore_path.read_text(encoding="utf-8")
    assert ".git" in content
    assert ".venv" in content
    assert ".env" in content
    assert "__pycache__" in content
