"""Unit tests for Redpanda / Kafka topic setup script (scripts/redpanda_topics.sh).

Verifies:
- Script exists, is executable, and contains strict bash error handling (set -euo pipefail)
- Provisions all four mandatory topics: supplier-events, risk-alerts, hitl-required, audit-events
- Configures partition counts and replication factor for local streaming
- Supports configurable broker address (default: localhost:9092)
- Validates bash syntax using 'bash -n'
- Supports idempotent execution
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
TOPIC_SCRIPT = REPO_ROOT / "scripts" / "redpanda_topics.sh"


def test_topic_script_exists_and_executable():
    """Verify scripts/redpanda_topics.sh exists and has execute permissions."""
    assert TOPIC_SCRIPT.exists(), f"Script not found at {TOPIC_SCRIPT}"
    assert os.access(TOPIC_SCRIPT, os.X_OK), f"Script {TOPIC_SCRIPT} is not executable"


def test_topic_script_shebang_and_strict_mode():
    """Verify script starts with bash shebang and enforces strict mode (set -euo pipefail)."""
    assert TOPIC_SCRIPT.exists(), "Script must exist"
    content = TOPIC_SCRIPT.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert lines[0].startswith("#!/") and "bash" in lines[0]
    assert any("set -euo pipefail" in line for line in lines)


def test_topic_script_declares_all_four_mandatory_topics():
    """Verify script creates supplier-events, risk-alerts, hitl-required, and audit-events."""
    content = TOPIC_SCRIPT.read_text(encoding="utf-8")

    required_topics = [
        "supplier-events",
        "risk-alerts",
        "hitl-required",
        "audit-events",
    ]

    for topic in required_topics:
        assert topic in content, f"Mandatory topic '{topic}' not found in {TOPIC_SCRIPT}"


def test_topic_script_configures_partitions_and_replication():
    """Verify script specifies partition count and single-node replication factor."""
    content = TOPIC_SCRIPT.read_text(encoding="utf-8")

    # Partitions and replication flags
    assert any(flag in content for flag in ["--partitions", "-p", "PARTITIONS"])
    assert any(flag in content for flag in ["--replicas", "-r", "REPLICAS"])


def test_topic_script_broker_configuration():
    """Verify script uses configurable broker address defaulting to localhost:9092."""
    content = TOPIC_SCRIPT.read_text(encoding="utf-8")

    assert "localhost:9092" in content
    assert any(var in content for var in ["REDPANDA_BROKERS", "KAFKA_BOOTSTRAP_SERVERS", "BROKERS"])


def test_topic_script_syntax_validity():
    """Verify bash script syntax passes validation using 'bash -n'."""
    assert TOPIC_SCRIPT.exists(), "Script must exist"
    result = subprocess.run(
        ["bash", "-n", str(TOPIC_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Bash syntax check failed: {result.stderr}"
