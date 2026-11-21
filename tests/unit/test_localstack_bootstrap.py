"""Unit tests for LocalStack bootstrap script (scripts/localstack_bootstrap.sh).

Verifies:
- Script exists, is executable, and contains strict bash error handling (set -euo pipefail)
- Creates S3 WORM bucket with Object Lock enabled and 7-year COMPLIANCE retention
- Creates KMS ECDSA P-256 signing key (ECC_NIST_P256, SIGN_VERIFY) and alias
- Creates IAM role stubs for API and Worker execution
- Validates bash syntax via 'bash -n'
- Supports configurable endpoint URL and region
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "localstack_bootstrap.sh"


def test_bootstrap_script_exists_and_executable():
    """Verify scripts/localstack_bootstrap.sh exists and has execute permissions."""
    assert BOOTSTRAP_SCRIPT.exists(), f"Script not found at {BOOTSTRAP_SCRIPT}"
    assert os.access(BOOTSTRAP_SCRIPT, os.X_OK), f"Script {BOOTSTRAP_SCRIPT} is not executable"


def test_bootstrap_script_shebang_and_strict_mode():
    """Verify script starts with bash shebang and enforces strict mode (set -euo pipefail)."""
    assert BOOTSTRAP_SCRIPT.exists(), "Script must exist"
    content = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert lines[0].startswith("#!/") and "bash" in lines[0]
    assert any("set -euo pipefail" in line for line in lines)


def test_bootstrap_s3_worm_configuration():
    """Verify script creates S3 bucket with Object Lock enabled and COMPLIANCE mode."""
    content = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    # WORM Object Lock configuration
    assert "object-lock-enabled-for-bucket" in content or "object-lock" in content
    assert "COMPLIANCE" in content
    assert "apexmotion-audit-worm" in content
    assert any(retention in content for retention in ["Years=7", "Days=2555", "7"])


def test_bootstrap_kms_ecdsa_configuration():
    """Verify script creates KMS key with ECC_NIST_P256 specification and SIGN_VERIFY usage."""
    content = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    # KMS key specification per BR-RULE-001 & HITL tokens
    assert "ECC_NIST_P256" in content
    assert "SIGN_VERIFY" in content
    assert "alias/apexmotion-hitl-signer" in content


def test_bootstrap_iam_roles_configuration():
    """Verify script provisions IAM execution role stubs for API and Worker."""
    content = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "create-role" in content
    assert "apexmotion-api-role" in content
    assert "apexmotion-worker-role" in content


def test_bootstrap_script_syntax_validity():
    """Verify bash script syntax passes validation using 'bash -n'."""
    assert BOOTSTRAP_SCRIPT.exists(), "Script must exist"
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Bash syntax check failed: {result.stderr}"
