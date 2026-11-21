"""Unit tests for Neptune local emulation (P2-4).

Verifies:
- docker-compose.yml defines neptune service with TinkerPop Gremlin Server, port 8182,
  container_name apexmotion-neptune, and healthcheck.
- scripts/neptune_seed.cypher exists and declares all mandatory node types and relationships,
  including NanoCore golden reference entities (SUP-NC-882, MCU-X91, PLT-MUC-01).
- scripts/neptune_smoke_test.sh exists, is executable, adheres to strict bash mode,
  supports dry-run / offline verification, and passes bash syntax check.
"""

import stat
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent


def test_docker_compose_neptune_service_declared():
    """Verify docker-compose.yml declares neptune service with port 8182 and healthcheck."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml not found"

    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "neptune" in services, "neptune service missing from docker-compose.yml"

    neptune_cfg = services["neptune"]
    assert "tinkerpop/gremlin-server" in neptune_cfg.get("image", ""), (
        f"Expected tinkerpop/gremlin-server image, got: {neptune_cfg.get('image')}"
    )
    assert neptune_cfg.get("container_name") == "apexmotion-neptune"

    ports = [str(p) for p in neptune_cfg.get("ports", [])]
    assert any("8182" in p for p in ports), f"Port 8182 not mapped for neptune. Found: {ports}"

    assert "healthcheck" in neptune_cfg, "Healthcheck missing for neptune service"
    networks = neptune_cfg.get("networks", [])
    assert "apexmotion-network" in networks


def test_neptune_seed_file_exists_and_content():
    """Verify scripts/neptune_seed.cypher exists and declares core node labels and golden entities."""
    seed_path = REPO_ROOT / "scripts" / "neptune_seed.cypher"
    assert seed_path.exists(), f"Seed cypher file not found at {seed_path}"

    content = seed_path.read_text(encoding="utf-8")

    # Mandatory node labels per CLAUDE.md Section 8.2 and FRD Section 5.2
    mandatory_labels = [
        "Supplier",
        "Component",
        "Plant",
        "Assembly",
        "Contract",
        "NewsEvent",
        "GeopoliticalRisk",
        "Program",
    ]
    for label in mandatory_labels:
        assert f":{label}" in content, f"Node label ':{label}' missing from neptune_seed.cypher"

    # NanoCore Golden Scenario reference identifiers
    assert "SUP-NC-882" in content, "NanoCore supplier ID 'SUP-NC-882' missing from seed"
    assert "MCU-X91" in content, "Component MPN 'MCU-X91' missing from seed"
    assert "PLT-MUC-01" in content, "Munich Plant ID 'PLT-MUC-01' missing from seed"
    assert "BetaElectro" in content or "SUP-BE-101" in content, "Tier-1 supplier missing from seed"


def test_neptune_seed_relationships_declared():
    """Verify scripts/neptune_seed.cypher declares all mandatory graph edges."""
    seed_path = REPO_ROOT / "scripts" / "neptune_seed.cypher"
    content = seed_path.read_text(encoding="utf-8")

    mandatory_edges = [
        "SUPPLIES",
        "PART_OF_BOM",
        "ASSEMBLED_AT",
        "ALLOCATED_TO",
        "BOUND_BY",
        "AFFECTS",
        "THREATENS",
        "TIER_1_OF",
    ]
    for edge in mandatory_edges:
        assert f":{edge}" in content, f"Edge type ':{edge}' missing from neptune_seed.cypher"


def test_smoke_test_script_exists_and_executable():
    """Verify scripts/neptune_smoke_test.sh exists and has execute permissions."""
    script_path = REPO_ROOT / "scripts" / "neptune_smoke_test.sh"
    assert script_path.exists(), f"Smoke test script not found at {script_path}"

    mode = script_path.stat().st_mode
    assert bool(mode & stat.S_IXUSR), (
        "scripts/neptune_smoke_test.sh is not executable (chmod +x required)"
    )


def test_smoke_test_script_shebang_and_strict_mode():
    """Verify script starts with bash shebang and activates strict bash error flags."""
    script_path = REPO_ROOT / "scripts" / "neptune_smoke_test.sh"
    content = script_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert lines[0].startswith("#!/") and "bash" in lines[0]
    assert any("set -euo pipefail" in line for line in lines)


def test_smoke_test_script_port_and_endpoint_defaults():
    """Verify smoke test script defaults to NEPTUNE_ENDPOINT=localhost and NEPTUNE_PORT=8182."""
    script_path = REPO_ROOT / "scripts" / "neptune_smoke_test.sh"
    content = script_path.read_text(encoding="utf-8")

    assert "NEPTUNE_ENDPOINT" in content
    assert "NEPTUNE_PORT" in content
    assert "8182" in content


def test_smoke_test_script_dry_run_execution():
    """Verify smoke test script executes cleanly in dry-run/mock mode with zero I/O."""
    script_path = REPO_ROOT / "scripts" / "neptune_smoke_test.sh"
    result = subprocess.run(
        [str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Dry-run failed: stdout={result.stdout}, stderr={result.stderr}"
    assert (
        "dry-run" in result.stdout.lower()
        or "mock" in result.stdout.lower()
        or "simulat" in result.stdout.lower()
    )


def test_smoke_test_script_syntax_validity():
    """Verify scripts/neptune_smoke_test.sh contains valid bash syntax using bash -n."""
    script_path = REPO_ROOT / "scripts" / "neptune_smoke_test.sh"
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Bash syntax check failed: {result.stderr}"
