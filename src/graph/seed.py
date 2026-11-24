"""Knowledge Graph Schema Seeder for Amazon Neptune (P5-2).

Declares canonical entity models, supply chain relationships, and executes
idempotent OpenCypher MERGE queries to seed the multi-tier automotive
knowledge graph.

Reference:
- CLAUDE.md Section 8.2 (Knowledge Graph Schema)
- FRD Section 5.2 (Multi-Tier Supply Chain Graph Model)
- NanoCore Reference Scenario (SUP-NC-882 -> MCU-X91 -> PLT-MUC-01)
"""

import time
from dataclasses import dataclass, field
from typing import Any

from src.api.exceptions import AppException
from src.core.logging import get_logger
from src.graph.neptune_client import NeptuneClient, NeptuneClientError

logger = get_logger("apexmotion.graph.seed")


class GraphSeedError(AppException):
    """Raised when Neptune graph seeding or verification fails."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="GRAPH_SEED_ERROR",
            message=message,
            status_code=500,
            details=details,
        )


@dataclass
class SeedResult:
    """Summary of Neptune graph schema seeding execution."""

    nodes_created: int
    relationships_created: int
    execution_time_ms: float
    success: bool
    details: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------
# Golden Reference Entities (CLAUDE.md Section 8.2 & FRD Section 5.2)
# ------------------------------------------------------------------------------

GOLDEN_SUPPLIERS: list[dict[str, Any]] = [
    {
        "id": "SUP-NC-882",
        "name": "NanoCore Semiconductor",
        "tier": 2,
        "country": "TW",
        "risk_score": 0.88,
        "aml_status": "CLEAR",
        "last_updated": "2026-11-20T10:00:00Z",
    },
    {
        "id": "SUP-BE-101",
        "name": "BetaElectro AG",
        "tier": 1,
        "country": "DE",
        "risk_score": 0.22,
        "aml_status": "CLEAR",
        "last_updated": "2026-11-20T10:00:00Z",
    },
    {
        "id": "SUP-VL-501",
        "name": "Volta Lithium Resources",
        "tier": 3,
        "country": "AU",
        "risk_score": 0.35,
        "aml_status": "CLEAR",
        "last_updated": "2026-11-20T10:00:00Z",
    },
    {
        "id": "SUP-MC-002",
        "name": "MicroChip Global Semiconductors",
        "tier": 2,
        "country": "US",
        "risk_score": 0.25,
        "aml_status": "CLEAR",
        "last_updated": "2026-11-20T10:00:00Z",
    },
    {
        "id": "SUP-SIL-901",
        "name": "Siltronic Silicon Wafers AG",
        "tier": 3,
        "country": "DE",
        "risk_score": 0.15,
        "aml_status": "CLEAR",
        "last_updated": "2026-11-20T10:00:00Z",
    },
]

GOLDEN_COMPONENTS: list[dict[str, Any]] = [
    {
        "id": "CMP-MCU-X91",
        "mpn": "MCU-X91",
        "sku": "SKU-77291",
        "description": "32-Bit Automotive Grade Microcontroller Unit",
        "criticality": "CRITICAL",
        "days_of_cover": 7.68,
        "daily_consumption_rate": 18500.0,
    },
    {
        "id": "CMP-PMIC-440",
        "mpn": "PMIC-440",
        "sku": "SKU-88120",
        "description": "High-Efficiency Power Management Integrated Circuit",
        "criticality": "HIGH",
        "days_of_cover": 14.5,
        "daily_consumption_rate": 9200.0,
    },
]

GOLDEN_PLANTS: list[dict[str, Any]] = [
    {
        "id": "PLT-MUC-01",
        "plant_id": "PLT-MUC-01",
        "name": "Munich Assembly Hub",
        "location": "Munich",
        "country": "DE",
        "region": "EMEA",
        "hourly_downtime_rate_usd": 92000.0,
        "rate_eur": 85000.0,
        "capacity": 500,
    },
    {
        "id": "PLT-BLR-02",
        "plant_id": "PLT-BLR-02",
        "name": "Bengaluru Electronics Facility",
        "location": "Bengaluru",
        "country": "IN",
        "region": "APAC",
        "hourly_downtime_rate_usd": 28000.0,
        "rate_eur": 25000.0,
        "capacity": 350,
    },
]

GOLDEN_CONTRACTS: list[dict[str, Any]] = [
    {
        "id": "CTR-NC-2024-01",
        "supplier_id": "SUP-NC-882",
        "value_usd": 2448105.00,
        "expiry_date": "2026-12-31",
        "payment_terms": "NET_60",
    },
    {
        "id": "CTR-BE-2023-09",
        "supplier_id": "SUP-BE-101",
        "value_usd": 18500000.00,
        "expiry_date": "2027-06-30",
        "payment_terms": "NET_45",
    },
]

GOLDEN_EXTERNAL_SIGNALS: list[dict[str, Any]] = [
    {
        "label": "NewsEvent",
        "id": "EVT-NEWS-2026-081",
        "headline": "Cleanroom facility fire reported at Hsinchu Science Park, wafer testing halted",
        "sentiment": -0.85,
        "source": "Reuters",
        "published_at": "2026-11-20T08:15:00Z",
    },
    {
        "label": "GeopoliticalRisk",
        "id": "RISK-GEO-TW-01",
        "region": "East Asia / Taiwan Strait",
        "risk_type": "EXPORT_RESTRICTION_LOGISTICS",
        "severity": "HIGH",
        "description": "Bilateral export controls and maritime shipping lane congestion in the Taiwan Strait corridor.",
    },
    {
        "label": "GeopoliticalRisk",
        "id": "RISK-GEO-TW-02",
        "region": "Northern Taiwan / Hsinchu",
        "risk_type": "SEISMIC_AND_POWER_VULNERABILITY",
        "severity": "HIGH",
        "description": "Subduction fault seismic activity and cleanroom power grid concentration across Hsinchu Science Park.",
    },
    {
        "label": "GeopoliticalRisk",
        "id": "RISK-GEO-TW-03",
        "region": "Taiwan Strait / South China Sea",
        "risk_type": "MARITIME_CHOKEPOINT_BLOCKADE",
        "severity": "CRITICAL",
        "description": "Airspace restrictions and naval blockade exercises threatening primary container shipping routes.",
    },
]

GOLDEN_ASSEMBLIES: list[dict[str, Any]] = [
    {
        "id": "ASM-BECU-04",
        "assembly_id": "ASM-BECU-04",
        "bom_rev": "4.2",
        "name": "High-Voltage Battery Electronic Control Unit (ECU)",
    }
]

GOLDEN_PROGRAMS: list[dict[str, Any]] = [
    {
        "id": "PRG-HGT-2026",
        "program_id": "PRG-HGT-2026",
        "model": "Apex Hyper-GT",
        "daily_target_units": 250,
        "margin": 14500.0,
        "margin_per_unit_usd": 14500.0,
    }
]

GOLDEN_RELATIONSHIPS: list[dict[str, Any]] = [
    # Supplier to Component
    {
        "from_label": "Supplier",
        "from_id": "SUP-NC-882",
        "type": "SUPPLIES",
        "to_label": "Component",
        "to_id": "CMP-MCU-X91",
        "props": {"contract_id": "CTR-NC-2024-01"},
    },
    {
        "from_label": "Supplier",
        "from_id": "SUP-NC-882",
        "type": "SUPPLIES_PART",
        "to_label": "Component",
        "to_id": "CMP-MCU-X91",
        "props": {"lead_time_days": 45, "is_single_source": True},
    },
    {
        "from_label": "Supplier",
        "from_id": "SUP-VL-501",
        "type": "SUPPLIES_PART",
        "to_label": "Component",
        "to_id": "CMP-PMIC-440",
        "props": {"lead_time_days": 60, "is_single_source": False},
    },
    {
        "from_label": "Supplier",
        "from_id": "SUP-MC-002",
        "type": "SUPPLIES_PART",
        "to_label": "Component",
        "to_id": "CMP-MCU-X91",
        "props": {"lead_time_days": 28, "is_single_source": False},
    },
    # Component to Plant
    {
        "from_label": "Component",
        "from_id": "CMP-MCU-X91",
        "type": "USED_BY",
        "to_label": "Plant",
        "to_id": "PLT-MUC-01",
        "props": {},
    },
    {
        "from_label": "Component",
        "from_id": "CMP-MCU-X91",
        "type": "USED_BY",
        "to_label": "Plant",
        "to_id": "PLT-BLR-02",
        "props": {},
    },
    {
        "from_label": "Component",
        "from_id": "CMP-PMIC-440",
        "type": "USED_BY",
        "to_label": "Plant",
        "to_id": "PLT-BLR-02",
        "props": {},
    },
    # Multi-Tier Chain: NanoCore (Tier 2) -> BetaElectro (Tier 1)
    {
        "from_label": "Supplier",
        "from_id": "SUP-NC-882",
        "type": "TIER_1_OF",
        "to_label": "Supplier",
        "to_id": "SUP-BE-101",
        "props": {},
    },
    # Multi-Tier Chain: Siltronic Wafers (Tier 3) -> NanoCore (Tier 2)
    {
        "from_label": "Supplier",
        "from_id": "SUP-SIL-901",
        "type": "TIER_1_OF",
        "to_label": "Supplier",
        "to_id": "SUP-NC-882",
        "props": {},
    },
    # Multi-Tier Chain: MicroChip (Tier 2) -> BetaElectro (Tier 1)
    {
        "from_label": "Supplier",
        "from_id": "SUP-MC-002",
        "type": "TIER_1_OF",
        "to_label": "Supplier",
        "to_id": "SUP-BE-101",
        "props": {},
    },
    # Component to Assembly BOM
    {
        "from_label": "Component",
        "from_id": "CMP-MCU-X91",
        "type": "PART_OF_BOM",
        "to_label": "Assembly",
        "to_id": "ASM-BECU-04",
        "props": {"quantity_per_assembly": 2},
    },
    # Assembly to Plant
    {
        "from_label": "Assembly",
        "from_id": "ASM-BECU-04",
        "type": "ASSEMBLED_AT",
        "to_label": "Plant",
        "to_id": "PLT-MUC-01",
        "props": {"primary_line": "Line-B"},
    },
    # Plant to Program
    {
        "from_label": "Plant",
        "from_id": "PLT-MUC-01",
        "type": "ALLOCATED_TO",
        "to_label": "Program",
        "to_id": "PRG-HGT-2026",
        "props": {"daily_build_quota": 250},
    },
    # Contractual Governance
    {
        "from_label": "Supplier",
        "from_id": "SUP-NC-882",
        "type": "BOUND_BY",
        "to_label": "Contract",
        "to_id": "CTR-NC-2024-01",
        "props": {},
    },
    {
        "from_label": "Supplier",
        "from_id": "SUP-BE-101",
        "type": "BOUND_BY",
        "to_label": "Contract",
        "to_id": "CTR-BE-2023-09",
        "props": {},
    },
    # External Incidents and Geopolitical Risks
    {
        "from_label": "NewsEvent",
        "from_id": "EVT-NEWS-2026-081",
        "type": "AFFECTS",
        "to_label": "Supplier",
        "to_id": "SUP-NC-882",
        "props": {},
    },
    {
        "from_label": "GeopoliticalRisk",
        "from_id": "RISK-GEO-TW-01",
        "type": "THREATENS",
        "to_label": "Supplier",
        "to_id": "SUP-NC-882",
        "props": {},
    },
    {
        "from_label": "GeopoliticalRisk",
        "from_id": "RISK-GEO-TW-02",
        "type": "THREATENS",
        "to_label": "Supplier",
        "to_id": "SUP-NC-882",
        "props": {},
    },
    {
        "from_label": "GeopoliticalRisk",
        "from_id": "RISK-GEO-TW-03",
        "type": "THREATENS",
        "to_label": "Supplier",
        "to_id": "SUP-NC-882",
        "props": {},
    },
]


def _format_cypher_value(val: Any) -> str:
    """Format Python values into valid OpenCypher literals."""
    if isinstance(val, str):
        escaped = val.replace("'", "\\'")
        return f"'{escaped}'"
    elif isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        return str(val)
    elif val is None:
        return "null"
    return f"'{val}'"


def get_seed_cypher_statements() -> list[str]:
    """Generate idempotent OpenCypher MERGE statements for all nodes and relationships.

    Returns:
        List of OpenCypher query strings.
    """
    statements: list[str] = []

    # 1. Supplier Nodes
    for s in GOLDEN_SUPPLIERS:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in s.items())
        statements.append(f"MERGE (n:Supplier {{id: '{s['id']}'}}) SET {props}")

    # 2. Component Nodes
    for c in GOLDEN_COMPONENTS:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in c.items())
        statements.append(f"MERGE (n:Component {{id: '{c['id']}'}}) SET {props}")

    # 3. Plant Nodes
    for p in GOLDEN_PLANTS:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in p.items())
        statements.append(f"MERGE (n:Plant {{id: '{p['id']}'}}) SET {props}")

    # 4. Contract Nodes
    for ct in GOLDEN_CONTRACTS:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in ct.items())
        statements.append(f"MERGE (n:Contract {{id: '{ct['id']}'}}) SET {props}")

    # 5. External Signals (NewsEvent, GeopoliticalRisk)
    for sig in GOLDEN_EXTERNAL_SIGNALS:
        label = sig["label"]
        attrs = {k: v for k, v in sig.items() if k != "label"}
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in attrs.items())
        statements.append(f"MERGE (n:{label} {{id: '{sig['id']}'}}) SET {props}")

    # 6. Assembly Nodes
    for a in GOLDEN_ASSEMBLIES:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in a.items())
        statements.append(f"MERGE (n:Assembly {{id: '{a['id']}'}}) SET {props}")

    # 7. Program Nodes
    for prg in GOLDEN_PROGRAMS:
        props = ", ".join(f"n.{k} = {_format_cypher_value(v)}" for k, v in prg.items())
        statements.append(f"MERGE (n:Program {{id: '{prg['id']}'}}) SET {props}")

    # 8. Relationships
    for r in GOLDEN_RELATIONSHIPS:
        from_label = r["from_label"]
        from_id = r["from_id"]
        rel_type = r["type"]
        to_label = r["to_label"]
        to_id = r["to_id"]
        props_dict = r.get("props", {})

        if props_dict:
            props_str = ", ".join(
                f"r.{k} = {_format_cypher_value(v)}" for k, v in props_dict.items()
            )
            cql = (
                f"MATCH (from:{from_label} {{id: '{from_id}'}}), (to:{to_label} {{id: '{to_id}'}}) "
                f"MERGE (from)-[r:{rel_type}]->(to) "
                f"SET {props_str}"
            )
        else:
            cql = (
                f"MATCH (from:{from_label} {{id: '{from_id}'}}), (to:{to_label} {{id: '{to_id}'}}) "
                f"MERGE (from)-[r:{rel_type}]->(to)"
            )
        statements.append(cql)

    return statements


async def seed_graph(
    client: NeptuneClient,
    clear_existing: bool = False,
) -> SeedResult:
    """Execute knowledge graph schema seed against Amazon Neptune.

    Args:
        client: Active NeptuneClient instance.
        clear_existing: If True, executes DETACH DELETE before seeding.

    Returns:
        SeedResult containing execution statistics and outcome.

    Raises:
        GraphSeedError: If any query execution fails.
    """
    start_time = time.perf_counter()
    logger.info("Starting Neptune graph schema seeding (clear_existing=%s)...", clear_existing)

    if clear_existing:
        logger.warning("Clearing all existing Neptune graph nodes and relationships...")
        try:
            await client.execute_query("MATCH (n) DETACH DELETE n")
        except NeptuneClientError as exc:
            logger.error("Failed to purge graph during seed: %s", exc)
            raise GraphSeedError(
                message=f"Failed to clear Neptune graph: {exc}",
                details={"stage": "clear_existing", "error": str(exc)},
            ) from exc

    statements = get_seed_cypher_statements()
    executed_count = 0

    total_nodes = (
        len(GOLDEN_SUPPLIERS)
        + len(GOLDEN_COMPONENTS)
        + len(GOLDEN_PLANTS)
        + len(GOLDEN_CONTRACTS)
        + len(GOLDEN_EXTERNAL_SIGNALS)
        + len(GOLDEN_ASSEMBLIES)
        + len(GOLDEN_PROGRAMS)
    )
    total_relationships = len(GOLDEN_RELATIONSHIPS)

    for i, cql in enumerate(statements):
        try:
            await client.execute_query(cql)
            executed_count += 1
        except NeptuneClientError as exc:
            logger.error("Failed executing seed statement %d/%d: %s", i + 1, len(statements), cql)
            raise GraphSeedError(
                message=f"Failed to execute seed query: {exc}",
                details={"statement_index": i, "query": cql, "error": str(exc)},
            ) from exc

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        "Neptune graph seeding completed successfully in %.2fms (%d statements executed)",
        elapsed_ms,
        executed_count,
    )

    return SeedResult(
        nodes_created=total_nodes,
        relationships_created=total_relationships,
        execution_time_ms=elapsed_ms,
        success=True,
        details={
            "statements_executed": executed_count,
            "clear_existing": clear_existing,
        },
    )


async def verify_seed_integrity(client: NeptuneClient) -> dict[str, Any]:
    """Verify that all mandatory graph entities and relationships exist in Neptune.

    Args:
        client: Active NeptuneClient instance.

    Returns:
        Dictionary report containing verification metrics, counts, and validation status.
    """
    logger.info("Verifying Neptune graph seed integrity...")
    node_labels = [
        "Supplier",
        "Component",
        "Plant",
        "Contract",
        "NewsEvent",
        "GeopoliticalRisk",
        "Assembly",
        "Program",
    ]
    counts: dict[str, int] = {}
    is_valid = True
    discrepancies: list[str] = []

    for label in node_labels:
        try:
            res = await client.execute_query(f"MATCH (n:{label}) RETURN count(n) AS count")
            count = res[0].get("count", 0) if res else 0
            counts[label] = int(count)
            if count == 0:
                is_valid = False
                discrepancies.append(f"Missing nodes for label ':{label}'")
        except Exception as exc:
            is_valid = False
            discrepancies.append(f"Query failed for label ':{label}': {exc}")

    # Check total relationships
    try:
        res = await client.execute_query("MATCH ()-[r]->() RETURN count(r) AS count")
        rel_count = res[0].get("count", 0) if res else 0
        counts["Relationships"] = int(rel_count)
        if rel_count == 0:
            is_valid = False
            discrepancies.append("No relationships found in graph")
    except Exception as exc:
        is_valid = False
        discrepancies.append(f"Query failed for relationships: {exc}")

    # Check golden NanoCore supplier existence
    golden_present = False
    try:
        res = await client.execute_query("MATCH (s:Supplier {id: 'SUP-NC-882'}) RETURN s.id AS id")
        golden_present = len(res) > 0 and res[0].get("id") == "SUP-NC-882"
        if not golden_present:
            is_valid = False
            discrepancies.append("Golden supplier NanoCore (SUP-NC-882) not found")
    except Exception as exc:
        is_valid = False
        discrepancies.append(f"Query failed for golden supplier: {exc}")

    # Check 3 geopolitical risk nodes threatening NanoCore
    geo_threats_present = False
    try:
        res = await client.execute_query(
            "MATCH (g:GeopoliticalRisk)-[:THREATENS]->(s:Supplier {id: 'SUP-NC-882'}) RETURN g.id AS id"
        )
        geo_ids = {r.get("id") for r in res}
        expected_threats = {"RISK-GEO-TW-01", "RISK-GEO-TW-02", "RISK-GEO-TW-03"}
        geo_threats_present = expected_threats.issubset(geo_ids)
        if not geo_threats_present:
            is_valid = False
            discrepancies.append(
                f"Missing geopolitical threats for NanoCore: {expected_threats - geo_ids}"
            )
    except Exception as exc:
        is_valid = False
        discrepancies.append(f"Query failed for geopolitical risk threats: {exc}")

    return {
        "is_valid": is_valid,
        "golden_entity_present": golden_present,
        "geopolitical_threats_present": geo_threats_present,
        "counts": counts,
        "discrepancies": discrepancies,
    }
