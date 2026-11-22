"""Unit tests for Neptune Knowledge Graph schema seed (P5-2).

Verifies:
- Declaration of mandatory node types: Supplier, Component, Plant, Contract, NewsEvent, GeopoliticalRisk, Assembly, Program.
- Declaration of mandatory supply chain relationships: SUPPLIES, SUPPLIES_PART, USED_BY, TIER_1_OF,
  PART_OF_BOM, ASSEMBLED_AT, ALLOCATED_TO, BOUND_BY, AFFECTS, THREATENS.
- Golden reference entities (NanoCore SUP-NC-882, MCU-X91, Munich Hub PLT-MUC-01, etc.).
- Generation of idempotent OpenCypher MERGE statements.
- Execution of seed_graph() using NeptuneClient.
- Optional graph purge (clear_existing=True).
- Robust error handling raising GraphSeedError on query failure.
- Verification of seed integrity via verify_seed_integrity().
- Dry-run execution of scripts/seed_neptune.py.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from src.graph.neptune_client import NeptuneClient, NeptuneClientError, NeptuneQueryError
from src.graph.seed import (
    GOLDEN_COMPONENTS,
    GOLDEN_CONTRACTS,
    GOLDEN_EXTERNAL_SIGNALS,
    GOLDEN_PLANTS,
    GOLDEN_RELATIONSHIPS,
    GOLDEN_SUPPLIERS,
    GraphSeedError,
    SeedResult,
    get_seed_cypher_statements,
    seed_graph,
    verify_seed_integrity,
)

REPO_ROOT = Path(__file__).parent.parent.parent


def test_seed_declarations_and_golden_entities():
    """Verify golden entities for NanoCore scenario are present in seed definitions."""
    # Suppliers
    supplier_ids = {s["id"] for s in GOLDEN_SUPPLIERS}
    assert "SUP-NC-882" in supplier_ids  # NanoCore Semiconductor (Tier 2)
    assert "SUP-BE-101" in supplier_ids  # BetaElectro AG (Tier 1)
    assert "SUP-VL-501" in supplier_ids  # Volta Lithium (Tier 3)

    # Components
    component_mpns = {c["mpn"] for c in GOLDEN_COMPONENTS}
    assert "MCU-X91" in component_mpns
    assert "PMIC-440" in component_mpns

    # Plants
    plant_ids = {p["id"] for p in GOLDEN_PLANTS}
    assert "PLT-MUC-01" in plant_ids  # Munich Assembly Hub
    assert "PLT-BLR-02" in plant_ids  # Bengaluru Electronics Facility

    # Contracts
    contract_ids = {c["id"] for c in GOLDEN_CONTRACTS}
    assert "CTR-NC-2024-01" in contract_ids
    assert "CTR-BE-2023-09" in contract_ids

    # Signals
    signal_ids = {s["id"] for s in GOLDEN_EXTERNAL_SIGNALS}
    assert "EVT-NEWS-2026-081" in signal_ids
    assert "RISK-GEO-TW-01" in signal_ids


def test_seed_mandatory_relationship_types():
    """Verify all mandatory relationships from CLAUDE.md Sec 8.2 and FRD Sec 5.2 are defined."""
    rel_types = {r["type"] for r in GOLDEN_RELATIONSHIPS}
    mandatory_rels = {
        "SUPPLIES",
        "SUPPLIES_PART",
        "USED_BY",
        "TIER_1_OF",
        "PART_OF_BOM",
        "ASSEMBLED_AT",
        "ALLOCATED_TO",
        "BOUND_BY",
        "AFFECTS",
        "THREATENS",
    }
    for rel in mandatory_rels:
        assert rel in rel_types, f"Mandatory relationship '{rel}' missing from seed definitions"


def test_get_seed_cypher_statements_idempotency():
    """Verify generated Cypher statements use MERGE for idempotency."""
    statements = get_seed_cypher_statements()
    assert len(statements) > 0

    # Ensure every statement is a MERGE statement
    for stmt in statements:
        assert "MERGE" in stmt, f"Statement should use MERGE for idempotency: {stmt}"

    # Verify key labels are covered
    full_cql = "\n".join(statements)
    for label in ["Supplier", "Component", "Plant", "Contract", "NewsEvent", "GeopoliticalRisk"]:
        assert f":{label}" in full_cql, f"Label :{label} missing from generated statements"


@pytest.mark.asyncio
async def test_seed_graph_success():
    """Verify seed_graph() executes all statements and returns SeedResult."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.return_value = [{"count": 1}]

    result = await seed_graph(mock_client, clear_existing=False)

    assert isinstance(result, SeedResult)
    assert result.success is True
    assert result.nodes_created == (
        len(GOLDEN_SUPPLIERS)
        + len(GOLDEN_COMPONENTS)
        + len(GOLDEN_PLANTS)
        + len(GOLDEN_CONTRACTS)
        + len(GOLDEN_EXTERNAL_SIGNALS)
        + 2  # Assembly + Program
    )
    assert result.relationships_created == len(GOLDEN_RELATIONSHIPS)
    assert mock_client.execute_query.call_count == len(get_seed_cypher_statements())


@pytest.mark.asyncio
async def test_seed_graph_clear_existing():
    """Verify seed_graph() executes purge query when clear_existing is True."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.return_value = []

    await seed_graph(mock_client, clear_existing=True)

    # First call should be DETACH DELETE
    first_call_args = mock_client.execute_query.call_args_list[0]
    query_str = first_call_args[0][0]
    assert "DETACH DELETE" in query_str


@pytest.mark.asyncio
async def test_seed_graph_query_error_raises_graph_seed_error():
    """Verify execution failure raises GraphSeedError."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneQueryError("Syntax error in MERGE")

    with pytest.raises(GraphSeedError) as exc_info:
        await seed_graph(mock_client)

    assert "Failed to execute seed query" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_seed_integrity_success():
    """Verify verify_seed_integrity returns is_valid=True when expected entities exist."""
    mock_client = AsyncMock(spec=NeptuneClient)

    # Mock response returns count > 0 for each verification query
    mock_client.execute_query.side_effect = [
        [{"count": 3}],  # Supplier
        [{"count": 2}],  # Component
        [{"count": 2}],  # Plant
        [{"count": 2}],  # Contract
        [{"count": 1}],  # NewsEvent
        [{"count": 1}],  # GeopoliticalRisk
        [{"count": 1}],  # Assembly
        [{"count": 1}],  # Program
        [{"count": 10}],  # Relationships
        [{"id": "SUP-NC-882"}],  # Golden NanoCore check
    ]

    report = await verify_seed_integrity(mock_client)

    assert report["is_valid"] is True
    assert report["golden_entity_present"] is True
    assert report["counts"]["Supplier"] == 3
    assert report["counts"]["Component"] == 2


@pytest.mark.asyncio
async def test_verify_seed_integrity_missing_golden():
    """Verify verify_seed_integrity returns is_valid=False when golden entity missing."""
    mock_client = AsyncMock(spec=NeptuneClient)

    # Mock returns 0 or empty for golden entity
    mock_client.execute_query.side_effect = [
        [{"count": 3}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 1}],
        [{"count": 1}],
        [{"count": 1}],
        [{"count": 1}],
        [{"count": 10}],
        [],  # Empty results for NanoCore
    ]

    report = await verify_seed_integrity(mock_client)
    assert report["is_valid"] is False
    assert report["golden_entity_present"] is False


def test_cli_seed_script_dry_run():
    """Verify CLI script scripts/seed_neptune.py executes cleanly in --dry-run mode."""
    script_path = REPO_ROOT / "scripts" / "seed_neptune.py"
    assert script_path.exists(), f"Seed script {script_path} not found"

    result = subprocess.run(
        [sys.executable, str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Script failed with output: {result.stderr}"
    assert "ApexMotion Neptune Knowledge Graph Seeder" in result.stdout
    assert "Dry-run mode" in result.stdout or "[dry-run]" in result.stdout


def test_format_cypher_value_edge_cases():
    """Verify _format_cypher_value handles various Python data types."""
    from src.graph.seed import _format_cypher_value

    assert _format_cypher_value("O'Connor") == "'O\\'Connor'"
    assert _format_cypher_value(True) == "true"
    assert _format_cypher_value(False) == "false"
    assert _format_cypher_value(123) == "123"
    assert _format_cypher_value(45.67) == "45.67"
    assert _format_cypher_value(None) == "null"
    assert _format_cypher_value(["list"]) == "'['list']'"


@pytest.mark.asyncio
async def test_seed_graph_clear_existing_failure():
    """Verify seed_graph raises GraphSeedError when DETACH DELETE fails."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneClientError("Neptune purge error")

    with pytest.raises(GraphSeedError) as exc_info:
        await seed_graph(mock_client, clear_existing=True)

    assert "Failed to clear Neptune graph" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_seed_integrity_exceptions_handled():
    """Verify verify_seed_integrity gracefully captures exceptions during queries."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneClientError(
        "Connection drop during verification"
    )

    report = await verify_seed_integrity(mock_client)
    assert report["is_valid"] is False
    assert report["golden_entity_present"] is False
    assert len(report["discrepancies"]) > 0
