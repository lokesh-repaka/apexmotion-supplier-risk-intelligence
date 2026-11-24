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


def test_seed_declarations_and_golden_entities() -> None:
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


def test_seed_mandatory_relationship_types() -> None:
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


def test_get_seed_cypher_statements_idempotency() -> None:
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
async def test_seed_graph_success() -> None:
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
async def test_seed_graph_clear_existing() -> None:
    """Verify seed_graph() executes purge query when clear_existing is True."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.return_value = []

    await seed_graph(mock_client, clear_existing=True)

    # First call should be DETACH DELETE
    first_call_args = mock_client.execute_query.call_args_list[0]
    query_str = first_call_args[0][0]
    assert "DETACH DELETE" in query_str


@pytest.mark.asyncio
async def test_seed_graph_query_error_raises_graph_seed_error() -> None:
    """Verify execution failure raises GraphSeedError."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneQueryError("Syntax error in MERGE")

    with pytest.raises(GraphSeedError) as exc_info:
        await seed_graph(mock_client)

    assert "Failed to execute seed query" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_seed_integrity_success() -> None:
    """Verify verify_seed_integrity returns is_valid=True when expected entities exist."""
    mock_client = AsyncMock(spec=NeptuneClient)

    # Mock response returns count > 0 for each verification query
    mock_client.execute_query.side_effect = [
        [{"count": 5}],  # Supplier
        [{"count": 2}],  # Component
        [{"count": 2}],  # Plant
        [{"count": 2}],  # Contract
        [{"count": 1}],  # NewsEvent
        [{"count": 3}],  # GeopoliticalRisk
        [{"count": 1}],  # Assembly
        [{"count": 1}],  # Program
        [{"count": 17}],  # Relationships
        [{"id": "SUP-NC-882"}],  # Golden NanoCore check
        [
            {"id": "RISK-GEO-TW-01"},
            {"id": "RISK-GEO-TW-02"},
            {"id": "RISK-GEO-TW-03"},
        ],  # 3 Geo risks
    ]

    report = await verify_seed_integrity(mock_client)

    assert report["is_valid"] is True
    assert report["golden_entity_present"] is True
    assert report["geopolitical_threats_present"] is True
    assert report["counts"]["Supplier"] == 5
    assert report["counts"]["Component"] == 2
    assert report["counts"]["GeopoliticalRisk"] == 3


@pytest.mark.asyncio
async def test_verify_seed_integrity_missing_golden() -> None:
    """Verify verify_seed_integrity returns is_valid=False when golden entity missing."""
    mock_client = AsyncMock(spec=NeptuneClient)

    # Mock returns 0 or empty for golden entity
    mock_client.execute_query.side_effect = [
        [{"count": 5}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 1}],
        [{"count": 3}],
        [{"count": 1}],
        [{"count": 1}],
        [{"count": 17}],
        [],  # Empty results for NanoCore
        [],  # Empty results for geopolitical threats
    ]

    report = await verify_seed_integrity(mock_client)
    assert report["is_valid"] is False
    assert report["golden_entity_present"] is False


@pytest.mark.asyncio
async def test_verify_seed_integrity_missing_geopolitical_threat() -> None:
    """Verify verify_seed_integrity returns is_valid=False when a geopolitical threat node is missing."""
    mock_client = AsyncMock(spec=NeptuneClient)

    mock_client.execute_query.side_effect = [
        [{"count": 5}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 2}],
        [{"count": 1}],
        [{"count": 3}],
        [{"count": 1}],
        [{"count": 1}],
        [{"count": 17}],
        [{"id": "SUP-NC-882"}],  # NanoCore present
        [{"id": "RISK-GEO-TW-01"}],  # Only 1 of 3 geopolitical threats returned
    ]

    report = await verify_seed_integrity(mock_client)
    assert report["is_valid"] is False
    assert report["geopolitical_threats_present"] is False
    assert any("Missing geopolitical threats" in d for d in report["discrepancies"])


def test_cli_seed_script_dry_run() -> None:
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


def test_format_cypher_value_edge_cases() -> None:
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
async def test_seed_graph_clear_existing_failure() -> None:
    """Verify seed_graph raises GraphSeedError when DETACH DELETE fails."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneClientError("Neptune purge error")

    with pytest.raises(GraphSeedError) as exc_info:
        await seed_graph(mock_client, clear_existing=True)

    assert "Failed to clear Neptune graph" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_seed_integrity_exceptions_handled() -> None:
    """Verify verify_seed_integrity gracefully captures exceptions during queries."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.side_effect = NeptuneClientError(
        "Connection drop during verification"
    )

    report = await verify_seed_integrity(mock_client)
    assert report["is_valid"] is False
    assert report["golden_entity_present"] is False
    assert len(report["discrepancies"]) > 0


# ------------------------------------------------------------------------------
# P13-2: Multi-Tier Sourcing, Supplier-Component-Plant Edges, and 3 Geopolitical Risks
# ------------------------------------------------------------------------------


def test_seed_three_geopolitical_risk_nodes_for_nanocore_region() -> None:
    """Verify 3 distinct geopolitical risk nodes for the NanoCore Taiwan region (P13-2)."""
    geo_nodes = [sig for sig in GOLDEN_EXTERNAL_SIGNALS if sig.get("label") == "GeopoliticalRisk"]
    geo_ids = {g["id"] for g in geo_nodes}

    # Must contain exactly 3 geopolitical risk nodes in the Taiwan/East Asia region
    assert len(geo_nodes) == 3, f"Expected 3 geopolitical risk nodes, got {len(geo_nodes)}"
    assert "RISK-GEO-TW-01" in geo_ids  # Export controls & logistics
    assert "RISK-GEO-TW-02" in geo_ids  # Seismic / cleanroom power grid vulnerability
    assert "RISK-GEO-TW-03" in geo_ids  # Taiwan Strait maritime chokepoint blockade

    for g in geo_nodes:
        assert g["region"] in [
            "East Asia / Taiwan Strait",
            "Northern Taiwan / Hsinchu",
            "Taiwan Strait / South China Sea",
            "East Asia",
        ]
        assert g["severity"] in ["HIGH", "CRITICAL"]

    # Verify all 3 geopolitical risk nodes threaten NanoCore Semiconductor (SUP-NC-882)
    threat_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] == "THREATENS"
        and r["from_label"] == "GeopoliticalRisk"
        and r["to_id"] == "SUP-NC-882"
    ]
    threatened_by = {r["from_id"] for r in threat_rels}
    assert threatened_by == {"RISK-GEO-TW-01", "RISK-GEO-TW-02", "RISK-GEO-TW-03"}


def test_seed_supplier_component_plant_edges() -> None:
    """Verify supplier -> component -> plant edges and BOM assembly links (P13-2)."""
    # 1. Supplier -> Component relationships
    supplier_comp_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] in ("SUPPLIES", "SUPPLIES_PART")
        and r["from_label"] == "Supplier"
        and r["to_label"] == "Component"
    ]
    assert len(supplier_comp_rels) >= 3

    # Primary and alternate suppliers for canonical MCU-X91
    mcu_suppliers = {r["from_id"] for r in supplier_comp_rels if r["to_id"] == "CMP-MCU-X91"}
    assert "SUP-NC-882" in mcu_suppliers  # NanoCore primary single-source
    assert "SUP-MC-002" in mcu_suppliers  # MicroChip AML qualified secondary source

    # 2. Component -> Plant relationships
    comp_plant_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] == "USED_BY" and r["from_label"] == "Component" and r["to_label"] == "Plant"
    ]
    assert len(comp_plant_rels) >= 2
    mcu_plants = {r["to_id"] for r in comp_plant_rels if r["from_id"] == "CMP-MCU-X91"}
    assert "PLT-MUC-01" in mcu_plants  # Munich Hub directly consumes MCU-X91

    # 3. Component -> Assembly BOM -> Plant
    bom_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] == "PART_OF_BOM" and r["to_id"] == "ASM-BECU-04"
    ]
    assert len(bom_rels) >= 1
    assembly_plant_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] == "ASSEMBLED_AT" and r["from_id"] == "ASM-BECU-04"
    ]
    assert len(assembly_plant_rels) >= 1


def test_seed_tier_chain_links() -> None:
    """Verify multi-tier chain relationships (Tier 3 -> Tier 2 -> Tier 1) (P13-2)."""
    tier_rels = [
        r
        for r in GOLDEN_RELATIONSHIPS
        if r["type"] == "TIER_1_OF"
        and r["from_label"] == "Supplier"
        and r["to_label"] == "Supplier"
    ]
    assert len(tier_rels) >= 3, f"Expected >= 3 TIER_1_OF relationships, got {len(tier_rels)}"

    # Check Tier-3 raw wafer supplier to Tier-2 NanoCore fab
    wafer_to_nanocore = any(
        r["from_id"] == "SUP-SIL-901" and r["to_id"] == "SUP-NC-882" for r in tier_rels
    )
    assert wafer_to_nanocore, "Missing Tier-3 Siltronic to Tier-2 NanoCore TIER_1_OF link"

    # Check Tier-2 NanoCore to Tier-1 BetaElectro integrator
    nanocore_to_betElectro = any(
        r["from_id"] == "SUP-NC-882" and r["to_id"] == "SUP-BE-101" for r in tier_rels
    )
    assert nanocore_to_betElectro, "Missing Tier-2 NanoCore to Tier-1 BetaElectro TIER_1_OF link"

    # Check Tier-2 MicroChip to Tier-1 BetaElectro AML link
    microchip_to_betElectro = any(
        r["from_id"] == "SUP-MC-002" and r["to_id"] == "SUP-BE-101" for r in tier_rels
    )
    assert microchip_to_betElectro, "Missing Tier-2 MicroChip to Tier-1 BetaElectro TIER_1_OF link"


def test_cypher_seed_file_contains_three_geopolitical_nodes_and_tier_chains() -> None:
    """Verify scripts/neptune_seed.cypher declares all 3 geopolitical nodes and tier links."""
    cypher_path = REPO_ROOT / "scripts" / "neptune_seed.cypher"
    assert cypher_path.exists()
    content = cypher_path.read_text(encoding="utf-8")

    assert "RISK-GEO-TW-01" in content
    assert "RISK-GEO-TW-02" in content
    assert "RISK-GEO-TW-03" in content
    assert "SUP-SIL-901" in content
    assert "SUP-MC-002" in content
    assert "TIER_1_OF" in content
