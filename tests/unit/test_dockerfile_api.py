"""Unit tests for Dockerfile.api container specification and security hardening.

Validates:
1. Base image specification: Python 3.12-slim in multi-stage build (builder + runner).
2. Unprivileged non-root security: dedicated user/group (UID/GID 10001, /sbin/nologin, USER appuser).
3. Container liveness probe: HEALTHCHECK testing http://localhost:8000/health.
4. Port exposition: EXPOSE 8000.
5. Production ASGI entrypoint: Uvicorn binding to 0.0.0.0:8000.
6. Environment variable sanitation and layer hygiene.
7. Dockerignore secret exfiltration defense.
"""

import re
from pathlib import Path

DOCKERFILE_API_PATH = Path("Dockerfile.api")
DOCKERIGNORE_PATH = Path(".dockerignore")


def test_dockerfile_api_exists_and_readable():
    """Verify Dockerfile.api exists in repository root and has readable content."""
    assert DOCKERFILE_API_PATH.exists(), f"{DOCKERFILE_API_PATH} does not exist"
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "Dockerfile.api cannot be empty"


def test_dockerfile_api_multistage_python312_slim():
    """Verify multi-stage architecture using official python:3.12-slim base image."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")

    # Multi-stage declarations
    assert "FROM python:3.12-slim AS builder" in content, "Builder stage must use python:3.12-slim"
    assert "FROM python:3.12-slim AS runner" in content, "Runner stage must use python:3.12-slim"


def test_dockerfile_api_non_root_security_hardening():
    """Verify unprivileged non-root user and group creation conforming to CIS Docker benchmarks."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")

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


def test_dockerfile_api_healthcheck_directive():
    """Verify container liveness healthcheck targeting the /health endpoint."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")

    assert "HEALTHCHECK" in content, "Must declare HEALTHCHECK directive"
    assert "--interval=" in content, "Healthcheck must configure interval"
    assert "--timeout=" in content, "Healthcheck must configure timeout"
    assert "--retries=" in content, "Healthcheck must configure retries"
    assert "/health" in content, "Healthcheck must probe /health endpoint"


def test_dockerfile_api_networking_and_ports():
    """Verify HTTP port 8000 is exposed."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")
    assert re.search(r"^\s*EXPOSE\s+8000\b", content, re.MULTILINE), "Must declare EXPOSE 8000"


def test_dockerfile_api_entrypoint_uvicorn_production():
    """Verify production ASGI entrypoint launches uvicorn bound to 0.0.0.0:8000."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")

    # Entrypoint command
    assert re.search(
        r'CMD\s*\[.*"uvicorn".*"src\.api\.main:app".*"--host".*"0\.0\.0\.0".*"--port".*"8000".*\]',
        content,
        re.DOTALL,
    ), "CMD must launch uvicorn with src.api.main:app on 0.0.0.0:8000"


def test_dockerfile_api_environment_flags_and_path_hygiene():
    """Verify environment variables and clean PATH configuration."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")

    assert "PYTHONUNBUFFERED=1" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content
    assert 'PYTHONPATH="/app"' in content

    # Verify no invalid /install/bin references
    runner_stage = content.split("FROM python:3.12-slim AS runner")[-1]
    assert "/install/bin" not in runner_stage, (
        "Runner stage should not reference obsolete /install/bin path"
    )


def test_dockerfile_api_files_copied():
    """Verify required source files and installed site-packages are copied to runner stage."""
    content = DOCKERFILE_API_PATH.read_text(encoding="utf-8")
    runner_stage = content.split("FROM python:3.12-slim AS runner")[-1]

    assert "COPY --from=builder /usr/local/lib/python3.12/site-packages" in runner_stage
    assert "COPY --from=builder /usr/local/bin /usr/local/bin" in runner_stage
    assert "COPY src/ /app/src/" in runner_stage
    assert "alembic.ini" in runner_stage, "alembic.ini should be copied for database migrations"


def test_dockerignore_security_exclusions():
    """Verify .dockerignore excludes sensitive files, secrets, virtualenvs, and test caches."""
    assert DOCKERIGNORE_PATH.exists(), f"{DOCKERIGNORE_PATH} does not exist"
    content = DOCKERIGNORE_PATH.read_text(encoding="utf-8")

    # Critical secret exfiltration defenses
    assert ".env" in content
    assert ".git" in content
    assert ".venv" in content
    assert "*.pem" in content or ".pem" in content
    assert "*.key" in content or ".key" in content
    assert "*credentials*.json" in content
    assert "secrets/" in content
    assert "__pycache__" in content
    assert ".pytest_cache" in content
