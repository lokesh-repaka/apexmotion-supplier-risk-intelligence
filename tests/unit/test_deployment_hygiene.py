"""Unit test suite for deployment hygiene and security compliance (P16-6).

Validates:
1. Zero secret .env files committed to git tracking.
2. .gitignore and .dockerignore defense-in-depth secret exclusions.
3. Zero static AWS credentials (AKIA...) or plaintext private keys in codebase.
4. S3 WORM Object Lock in strict COMPLIANCE mode with 7-year statutory hold.
5. Container and Kubernetes non-root privilege escalation prevention.
6. GitHub Actions OIDC credentialing without long-lived static secrets.
7. Verification CLI utility (`scripts/verify_deployment_hygiene.py`).
"""

import re
import subprocess
from pathlib import Path

S3_WORM_TF = Path("infrastructure/terraform/s3_worm.tf")
VERIFY_SCRIPT = Path("scripts/verify_deployment_hygiene.py")


def test_no_env_files_tracked_in_git() -> None:
    """Verify that zero secret .env files are tracked in the Git repository."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = result.stdout.strip().splitlines()
    env_files = [f for f in tracked_files if ".env" in Path(f).name]

    # Only .env.example or template files are permitted
    allowed_env_names = {".env.example", ".env.test.example"}
    violations = [f for f in env_files if Path(f).name not in allowed_env_names]
    assert len(violations) == 0, f"Disallowed .env files tracked in Git: {violations}"


def test_gitignore_enforces_env_exclusion() -> None:
    """Verify .gitignore contains explicit exclusions for .env files."""
    gitignore = Path(".gitignore")
    assert gitignore.exists(), "Missing .gitignore file"
    content = gitignore.read_text(encoding="utf-8")
    assert re.search(r"^\.env\*?", content, re.MULTILINE), ".gitignore must exclude .env files"


def test_dockerignore_enforces_env_and_secrets_exclusion() -> None:
    """Verify .dockerignore contains exclusions for secrets, credentials, and .env files."""
    dockerignore = Path(".dockerignore")
    assert dockerignore.exists(), "Missing .dockerignore file"
    content = dockerignore.read_text(encoding="utf-8")

    assert ".env" in content, ".dockerignore must exclude .env files"
    assert "*.pem" in content or "*.key" in content, ".dockerignore must exclude private keys"
    assert "*credentials*.json" in content or "credentials" in content, (
        ".dockerignore must exclude credentials"
    )


def test_no_static_aws_access_keys() -> None:
    """Verify zero static AWS Access Key IDs (AKIA...) exist in tracked files."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = result.stdout.strip().splitlines()
    akia_pattern = re.compile(r"AKIA[0-9A-Z]{16}")

    violations: list[str] = []
    for rel_path in tracked_files:
        p = Path(rel_path)
        if not p.is_file() or p.suffix in (".xlsx", ".png", ".jpg", ".ico", ".pyc"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            matches = akia_pattern.findall(text)
            if matches:
                violations.append(f"{rel_path}: {matches}")
        except Exception:
            continue

    assert len(violations) == 0, f"Static AWS Access Keys detected: {violations}"


def test_no_plaintext_private_keys() -> None:
    """Verify zero plaintext private keys exist in tracked files."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = result.stdout.strip().splitlines()
    private_key_pattern = re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")

    violations: list[str] = []
    for rel_path in tracked_files:
        p = Path(rel_path)
        if not p.is_file() or p.suffix in (".xlsx", ".png", ".jpg", ".ico", ".pyc"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if private_key_pattern.search(text):
                violations.append(rel_path)
        except Exception:
            continue

    assert len(violations) == 0, f"Plaintext private keys detected in: {violations}"


def test_s3_worm_object_lock_compliance_mode() -> None:
    """Verify S3 WORM audit bucket specifies Object Lock in COMPLIANCE mode."""
    assert S3_WORM_TF.exists(), f"Missing Terraform S3 WORM module: {S3_WORM_TF}"
    content = S3_WORM_TF.read_text(encoding="utf-8")

    assert "aws_s3_bucket_object_lock_configuration" in content
    assert re.search(r"object_lock_enabled\s*=\s*true", content)
    assert re.search(r'mode\s*=\s*"COMPLIANCE"', content), (
        "S3 Object Lock must be strictly in 'COMPLIANCE' mode, never 'GOVERNANCE'"
    )


def test_s3_worm_seven_year_statutory_hold() -> None:
    """Verify S3 WORM audit bucket enforces 7-year retention and multi-AZ KMS encryption."""
    assert S3_WORM_TF.exists(), f"Missing Terraform S3 WORM module: {S3_WORM_TF}"
    content = S3_WORM_TF.read_text(encoding="utf-8")
    var_tf = Path("infrastructure/terraform/variables.tf").read_text(encoding="utf-8")

    # Statutory 7-year hold: check reference to var.audit_retention_years and its default value of 7
    assert re.search(r"years\s*=\s*var\.audit_retention_years", content) or re.search(
        r"years\s*=\s*7", content
    ), "S3 WORM default retention period must reference audit_retention_years"
    assert re.search(r'variable\s+"audit_retention_years"[\s\S]*?default\s*=\s*7', var_tf), (
        "audit_retention_years must default to 7"
    )

    # Bucket versioning enabled
    assert re.search(r'status\s*=\s*"Enabled"', content)

    # Block public access
    assert re.search(r"block_public_acls\s*=\s*true", content)
    assert re.search(r"block_public_policy\s*=\s*true", content)
    assert re.search(r"ignore_public_acls\s*=\s*true", content)
    assert re.search(r"restrict_public_buckets\s*=\s*true", content)

    # KMS Encryption
    assert re.search(r'sse_algorithm\s*=\s*"aws:kms"', content)


def test_dockerfiles_non_root_execution() -> None:
    """Verify API and Worker Dockerfiles enforce unprivileged user execution (UID 10001)."""
    api_dockerfile = Path("Dockerfile.api")
    worker_dockerfile = Path("Dockerfile.worker")
    assert api_dockerfile.exists()
    assert worker_dockerfile.exists()

    for path in (api_dockerfile, worker_dockerfile):
        content = path.read_text(encoding="utf-8")
        assert "USER appuser" in content, f"{path} must switch to non-root USER appuser"
        assert "10001" in content, f"{path} must declare non-root UID/GID 10001"


def test_kubernetes_manifests_security_context_hygiene() -> None:
    """Verify Kubernetes manifests enforce non-root UID 10001 and drop ALL capabilities."""
    k8s_dir = Path("infrastructure/kubernetes")
    deployments = [k8s_dir / "api-deployment.yaml", k8s_dir / "worker-deployment.yaml"]

    for path in deployments:
        assert path.exists(), f"Missing manifest: {path}"
        content = path.read_text(encoding="utf-8")
        assert re.search(r"runAsNonRoot:\s*true", content)
        assert re.search(r"runAsUser:\s*10001", content)
        assert re.search(r"runAsGroup:\s*10001", content)
        assert re.search(r"allowPrivilegeEscalation:\s*false", content)
        assert "- ALL" in content


def test_github_workflows_oidc_role_assumption() -> None:
    """Verify all GitHub Actions CD workflows use OIDC role assumption without static AWS keys."""
    workflows_dir = Path(".github/workflows")
    cd_workflows = [workflows_dir / "cd-staging.yml", workflows_dir / "cd-production.yml"]

    for path in cd_workflows:
        assert path.exists(), f"Missing workflow: {path}"
        content = path.read_text(encoding="utf-8")
        assert "aws-actions/configure-aws-credentials" in content
        assert "role-to-assume" in content
        assert "AKIA" not in content


def test_deployment_hygiene_verification_script() -> None:
    """Verify that scripts/verify_deployment_hygiene.py exists, is executable, and passes cleanly."""
    assert VERIFY_SCRIPT.exists(), f"Missing deployment hygiene script: {VERIFY_SCRIPT}"
    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Hygiene script failed: {result.stderr or result.stdout}"
    assert "Deployment Hygiene Verification PASSED" in result.stdout
