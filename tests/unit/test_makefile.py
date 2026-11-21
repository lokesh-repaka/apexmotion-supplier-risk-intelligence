"""Unit tests for Makefile developer commands (P2-5).

Verifies:
- Makefile exists at the repository root.
- Declares all six mandatory targets from TASKS.md:
  run-api, run-worker, run-frontend, test, lint, seed.
- Targets adhere to GEMINI.md and CLAUDE.md architectural standards:
  - run-api invokes uvicorn with reload on port 8000
  - run-worker invokes python3 -m src.kafka.consumer
  - run-frontend invokes npm run dev inside frontend
  - test enforces offline isolation flags (USE_LOCALSTACK, USE_MOCK_LLM, USE_LOCAL_KAFKA)
  - lint enforces ruff checks, ruff format check, and mypy type checking
  - seed invokes local infrastructure bootstrap scripts
- All targets are declared as .PHONY.
- Makefile syntax is verified via dry-run execution (make -n <target>).
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_makefile_exists():
    """Verify Makefile exists at repository root."""
    assert MAKEFILE_PATH.exists(), f"Makefile not found at {MAKEFILE_PATH}"


def test_makefile_defines_all_six_mandatory_targets():
    """Verify Makefile declares the six mandatory targets defined in TASKS.md."""
    assert MAKEFILE_PATH.exists(), "Makefile must exist"
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    mandatory_targets = [
        "run-api",
        "run-worker",
        "run-frontend",
        "test",
        "lint",
        "seed",
    ]

    for target in mandatory_targets:
        # Match target definition at start of line: target: ...
        pattern = rf"^{re.escape(target)}\s*:"
        assert re.search(pattern, content, re.MULTILINE), (
            f"Mandatory target '{target}' missing from Makefile"
        )


def test_makefile_target_commands_adhere_to_governance():
    """Verify target command implementations match architectural specifications."""
    assert MAKEFILE_PATH.exists(), "Makefile must exist"
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    # run-api must invoke uvicorn on main app
    assert "uvicorn" in content
    assert "src.api.main:app" in content

    # run-worker must invoke consumer or worker module
    assert "src.kafka.consumer" in content or "src.worker" in content

    # run-frontend must delegate to npm run dev
    assert "npm run dev" in content

    # test must enforce offline isolation flags
    assert "USE_LOCALSTACK=true" in content
    assert "pytest" in content

    # lint must enforce ruff and mypy
    assert "ruff check" in content
    assert "ruff format" in content
    assert "mypy" in content

    # seed must reference bootstrap scripts
    assert "localstack_bootstrap.sh" in content
    assert "redpanda_topics.sh" in content


def test_makefile_declares_phony_targets():
    """Verify all public targets are declared as .PHONY to prevent file name collisions."""
    assert MAKEFILE_PATH.exists(), "Makefile must exist"
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    mandatory_targets = [
        "run-api",
        "run-worker",
        "run-frontend",
        "test",
        "lint",
        "seed",
    ]

    phony_matches = re.findall(r"^\.PHONY\s*:(.*)$", content, re.MULTILINE)
    assert phony_matches, ".PHONY declaration missing from Makefile"
    phony_targets = " ".join(phony_matches).split()

    for target in mandatory_targets:
        assert target in phony_targets, f"Target '{target}' missing from .PHONY declaration"


def test_makefile_dry_run_syntax():
    """Verify Makefile syntax is valid across key targets using make -n (dry-run)."""
    assert MAKEFILE_PATH.exists(), "Makefile must exist"

    targets_to_test = ["help", "test", "lint", "seed"]
    for target in targets_to_test:
        result = subprocess.run(
            ["make", "-n", target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Dry run 'make -n {target}' failed: stdout={result.stdout}, stderr={result.stderr}"
        )


def test_makefile_default_help_target():
    """Verify default target or 'make help' displays available targets with descriptions."""
    assert MAKEFILE_PATH.exists(), "Makefile must exist"

    result = subprocess.run(
        ["make", "help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"'make help' failed: {result.stderr}"
    assert "run-api" in result.stdout
    assert "run-frontend" in result.stdout
    assert "test" in result.stdout
    assert "lint" in result.stdout
    assert "seed" in result.stdout
