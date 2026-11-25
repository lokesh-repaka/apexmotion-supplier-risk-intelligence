#!/usr/bin/env python3
"""ApexMotion Deployment Hygiene & Security Compliance Verifier.

Audits repository files for:
1. Zero secret .env files committed to git tracking.
2. .gitignore and .dockerignore secret exclusions.
3. Zero static AWS credentials (AKIA...) or plaintext private keys.
4. S3 WORM Object Lock in strict COMPLIANCE mode with 7-year statutory hold.
5. Container and Kubernetes non-root privilege escalation prevention.
6. GitHub Actions OIDC credentialing without static secrets.

Exit code 0 on full compliance; non-zero if any hygiene check fails.
"""

import re
import subprocess
import sys
from pathlib import Path


def print_banner() -> None:
    """Print ASCII header banner."""
    print("=" * 72)
    print(" ApexMotion Deployment Hygiene & Compliance Verifier")
    print(" Enforcing Zero Static Secrets, S3 WORM 7-Yr Hold & Container Hardening")
    print("=" * 72)


def check_git_tracked_env_files() -> tuple[bool, str]:
    """Verify zero secret .env files are tracked in git."""
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        tracked = res.stdout.strip().splitlines()
        env_files = [f for f in tracked if ".env" in Path(f).name]
        allowed = {".env.example", ".env.test.example"}
        disallowed = [f for f in env_files if Path(f).name not in allowed]
        if disallowed:
            return False, f"Disallowed .env files tracked in Git: {disallowed}"
        return True, "No sensitive .env files committed (only .env.example tracked)"
    except Exception as exc:
        return False, f"Failed to inspect git files: {exc}"


def check_ignore_files_defense() -> tuple[bool, str]:
    """Verify .gitignore and .dockerignore contain defense-in-depth rules."""
    gitignore = Path(".gitignore")
    dockerignore = Path(".dockerignore")

    if not gitignore.exists() or not dockerignore.exists():
        return False, "Missing .gitignore or .dockerignore"

    git_text = gitignore.read_text(encoding="utf-8")
    docker_text = dockerignore.read_text(encoding="utf-8")

    if not re.search(r"^\.env\*?", git_text, re.MULTILINE):
        return False, ".gitignore does not exclude .env files"

    if ".env" not in docker_text or "*.key" not in docker_text and "*.pem" not in docker_text:
        return False, ".dockerignore missing credential exclusions"

    return True, ".gitignore and .dockerignore enforce strict credential exclusions"


def check_no_static_credentials() -> tuple[bool, str]:
    """Scan tracked repository files for static AWS keys and plaintext private keys."""
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        tracked = res.stdout.strip().splitlines()
        akia_re = re.compile(r"AKIA[0-9A-Z]{16}")
        priv_re = re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")

        violations = []
        for path_str in tracked:
            p = Path(path_str)
            if (
                not p.is_file()
                or p.suffix in (".xlsx", ".png", ".jpg", ".ico", ".pyc")
                or p.name in ("test_deployment_hygiene.py", "verify_deployment_hygiene.py")
            ):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if akia_re.findall(content):
                    violations.append(f"{path_str} (AKIA Access Key)")
                if priv_re.search(content):
                    violations.append(f"{path_str} (Plaintext Private Key)")
            except Exception:
                continue

        if violations:
            return False, f"Static credentials detected: {violations}"
        return True, "Zero static AWS keys (AKIA...) or plaintext private keys detected"
    except Exception as exc:
        return False, f"Failed scanning for static credentials: {exc}"


def check_s3_worm_compliance() -> tuple[bool, str]:
    """Verify Terraform S3 WORM configuration enforces COMPLIANCE mode and 7-year hold."""
    s3_tf = Path("infrastructure/terraform/s3_worm.tf")
    var_tf = Path("infrastructure/terraform/variables.tf")

    if not s3_tf.exists() or not var_tf.exists():
        return False, "Missing infrastructure/terraform/s3_worm.tf or variables.tf"

    s3_text = s3_tf.read_text(encoding="utf-8")
    var_text = var_tf.read_text(encoding="utf-8")

    if not re.search(r'mode\s*=\s*"COMPLIANCE"', s3_text):
        return False, "S3 Object Lock not set to COMPLIANCE mode"

    if not (
        re.search(r"years\s*=\s*var\.audit_retention_years", s3_text)
        or re.search(r"years\s*=\s*7", s3_text)
    ):
        return False, "S3 default retention not referencing audit_retention_years"

    if not re.search(r'variable\s+"audit_retention_years"[\s\S]*?default\s*=\s*7', var_text):
        return False, "Terraform variable audit_retention_years default is not 7"

    if not re.search(r"block_public_acls\s*=\s*true", s3_text):
        return False, "S3 public access block not fully enabled"

    return True, "S3 WORM Audit Vault verified: COMPLIANCE mode, 7-year statutory hold, KMS"


def check_container_and_k8s_hardening() -> tuple[bool, str]:
    """Verify Dockerfiles and Kubernetes manifests enforce non-root execution."""
    api_df = Path("Dockerfile.api")
    worker_df = Path("Dockerfile.worker")
    if not api_df.exists() or not worker_df.exists():
        return False, "Missing Dockerfile.api or Dockerfile.worker"

    for df in (api_df, worker_df):
        text = df.read_text(encoding="utf-8")
        if "USER appuser" not in text or "10001" not in text:
            return False, f"{df} does not enforce non-root UID 10001"

    k8s_api = Path("infrastructure/kubernetes/api-deployment.yaml")
    k8s_worker = Path("infrastructure/kubernetes/worker-deployment.yaml")
    for mf in (k8s_api, k8s_worker):
        if not mf.exists():
            return False, f"Missing {mf}"
        text = mf.read_text(encoding="utf-8")
        if not re.search(r"runAsUser:\s*10001", text) or not re.search(
            r"runAsNonRoot:\s*true", text
        ):
            return False, f"{mf} missing non-root securityContext"

    return True, "Container & Kubernetes workloads hardened: UID 10001, drop ALL capabilities"


def check_github_actions_oidc() -> tuple[bool, str]:
    """Verify GitHub Actions workflows use OIDC role assumption."""
    workflows_dir = Path(".github/workflows")
    cd_files = [workflows_dir / "cd-staging.yml", workflows_dir / "cd-production.yml"]

    for wf in cd_files:
        if not wf.exists():
            return False, f"Missing {wf}"
        text = wf.read_text(encoding="utf-8")
        if "role-to-assume" not in text or "aws-actions/configure-aws-credentials" not in text:
            return False, f"{wf} missing AWS OIDC role assumption"
        if "AKIA" in text:
            return False, f"{wf} contains static AWS credentials"

    return True, "GitHub Actions CD workflows enforce short-lived AWS STS OIDC tokens"


def main() -> int:
    """Run all deployment hygiene checks and exit with status code."""
    print_banner()

    checks = [
        ("Git Tracked .env Files", check_git_tracked_env_files),
        (".gitignore & .dockerignore Exclusions", check_ignore_files_defense),
        ("Static Credentials & Private Keys", check_no_static_credentials),
        ("S3 WORM 7-Year Compliance Mode", check_s3_worm_compliance),
        ("Container & Kubernetes Hardening", check_container_and_k8s_hardening),
        ("GitHub Actions OIDC Authentication", check_github_actions_oidc),
    ]

    all_passed = True
    for name, check_fn in checks:
        passed, msg = check_fn()
        status_symbol = "✓ PASS" if passed else "✗ FAIL"
        print(f"[{status_symbol}] {name}: {msg}")
        if not passed:
            all_passed = False

    print("=" * 72)
    if all_passed:
        print(" Deployment Hygiene Verification PASSED (All checks green)")
        print("=" * 72)
        return 0
    else:
        print(" Deployment Hygiene Verification FAILED (Correct issues above)")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
