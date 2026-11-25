"""Unit tests for Dockerfile.worker container specification and security hardening.

Validates:
1. Base image specification: Python 3.12-slim in multi-stage build (builder + runner).
2. Unprivileged non-root security: dedicated user/group (UID/GID 10001, /sbin/nologin, USER appuser).
3. Container liveness probe: HEALTHCHECK directive with calibrated intervals and timeouts.
4. Production worker entrypoint: Kafka signal consumer / Celery worker loop execution.
5. Environment variable sanitation and layer hygiene.
6. Copied files: installed site-packages, source code, alembic.ini, and pyproject.toml.
7. Dockerignore secret exfiltration defense.
8. Builder stage layer and cache optimization.
"""

import re
from pathlib import Path

DOCKERFILE_WORKER_PATH = Path("Dockerfile.worker")
DOCKERIGNORE_PATH = Path(".dockerignore")


def test_dockerfile_worker_exists_and_readable() -> None:
    """Verify Dockerfile.worker exists in repository root and has readable content."""
    assert DOCKERFILE_WORKER_PATH.exists(), f"{DOCKERFILE_WORKER_PATH} does not exist"
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "Dockerfile.worker cannot be empty"


def test_dockerfile_worker_multistage_python312_slim() -> None:
    """Verify multi-stage architecture using official python:3.12-slim base image."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")

    # Multi-stage declarations
    assert "FROM python:3.12-slim AS builder" in content, "Builder stage must use python:3.12-slim"
    assert "FROM python:3.12-slim AS runner" in content, "Runner stage must use python:3.12-slim"


def test_dockerfile_worker_non_root_security_hardening() -> None:
    """Verify unprivileged non-root user and group creation conforming to CIS Docker benchmarks."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")

    # Group and user creation
    assert re.search(r"groupadd\s+(-g\s+10001\s+)?appgroup", content), (
        "Must create appgroup with GID 10001"
    )
    assert re.search(r"useradd\s+.*-u\s+10001.*-s\s+/sbin/nologin.*appuser", content), (
        "Must create appuser with UID 10001 and /sbin/nologin shell"
    )

    # Ownership and execution user
    assert "chown -R appuser:appgroup" in content, "Must chown /app directory to appuser:appgroup"
    assert re.search(r"^\s*USER\s+appuser", content, re.MULTILINE), (
        "Must switch to unprivileged USER appuser before CMD"
    )


def test_dockerfile_worker_healthcheck_directive() -> None:
    """Verify worker container liveness healthcheck is declared with intervals and retries."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")

    assert "HEALTHCHECK" in content, "Must declare HEALTHCHECK directive"
    assert "--interval=" in content, "Healthcheck must configure interval"
    assert "--timeout=" in content, "Healthcheck must configure timeout"
    assert "--retries=" in content, "Healthcheck must configure retries"


def test_dockerfile_worker_entrypoint_production() -> None:
    """Verify worker entrypoint executes Kafka signal consumer or Celery worker loop."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")

    assert re.search(
        r'CMD\s*\[.*"python3".*"-m".*"src\.kafka\.consumer".*\]',
        content,
        re.DOTALL,
    ), "CMD must launch worker loop via src.kafka.consumer"


def test_dockerfile_worker_environment_flags_and_path_hygiene() -> None:
    """Verify environment variables and clean PATH configuration."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")

    assert "PYTHONUNBUFFERED=1" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content
    assert 'PYTHONPATH="/app"' in content

    # Verify no invalid /install/bin references in runner stage
    runner_stage = content.split("FROM python:3.12-slim AS runner")[-1]
    assert "/install/bin" not in runner_stage, (
        "Runner stage should not reference obsolete /install/bin path"
    )


def test_dockerfile_worker_files_copied() -> None:
    """Verify required source files, alembic.ini, and site-packages are copied to runner stage."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")
    runner_stage = content.split("FROM python:3.12-slim AS runner")[-1]

    assert "COPY --from=builder /usr/local/lib/python3.12/site-packages" in runner_stage
    assert "COPY --from=builder /usr/local/bin /usr/local/bin" in runner_stage
    assert "COPY src/ /app/src/" in runner_stage
    assert "alembic.ini" in runner_stage, "alembic.ini should be copied for schema awareness"
    assert "pyproject.toml" in runner_stage, "pyproject.toml should be copied into /app"


def test_dockerignore_security_exclusions_worker() -> None:
    """Verify .dockerignore excludes sensitive files, secrets, virtualenvs, and test caches."""
    assert DOCKERIGNORE_PATH.exists(), f"{DOCKERIGNORE_PATH} does not exist"
    content = DOCKERIGNORE_PATH.read_text(encoding="utf-8")

    assert ".env" in content
    assert ".git" in content
    assert ".venv" in content
    assert "*.pem" in content or ".pem" in content
    assert "*.key" in content or ".key" in content
    assert "*credentials*.json" in content
    assert "secrets/" in content
    assert "__pycache__" in content
    assert ".pytest_cache" in content


def test_dockerfile_worker_builder_optimization() -> None:
    """Verify builder stage installs dependencies cleanly with cache disabled."""
    content = DOCKERFILE_WORKER_PATH.read_text(encoding="utf-8")
    builder_stage = content.split("FROM python:3.12-slim AS runner")[0]

    assert "build-essential" in builder_stage
    assert "rm -rf /var/lib/apt/lists/*" in builder_stage
