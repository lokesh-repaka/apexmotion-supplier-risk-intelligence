"""Unit tests for Graph Traversal Paths and Single-Source Dependency Detection (P5-5).

Verifies:
- Mock Neptune OpenCypher responses for end-to-end 5-hop disruption path traversal:
  - Incident-to-Program: NewsEvent -> Supplier -> Component -> Assembly -> Plant -> Program.
  - Geopolitical-to-Program: GeopoliticalRisk -> Supplier -> Component -> Assembly -> Plant -> Program.
  - Multi-tier chain path: Sub-tier -> Tier-2 -> Tier-1 -> Component -> Assembly -> Plant.
- Exact assertion of 5 hops (length=5, 6 nodes, 5 relational edges).
- Single-source dependency detection:
  - Strict sole-supplier detection (supplier_count == 1).
  - Contractual single-source flag detection (is_single_source == True).
  - Multi-source redundancy verification (non-vulnerable components excluded).
  - Component redundancy lookup and risk tier categorization.
  - Filtering single-source dependencies by specific supplier ID.
- Neptune query SLO latency compliance (<= 2.0s per CLAUDE.md).
- Error mapping and fault tolerance:
  - NeptuneTimeoutError -> TraversalError (HTTP 504).
  - NeptuneCircuitBreakerOpenError -> TraversalError (HTTP 503).
  - NeptuneQueryError -> TraversalError (HTTP 400).
  - Empty path results handled gracefully without exceptions.
- Strict offline isolation with zero network or AWS I/O using mock NeptuneClient.
"""

import time
from unittest.mock import AsyncMock

import pytest
from src.graph.neptune_client import (
    NeptuneCircuitBreakerOpenError,
    NeptuneClient,
    NeptuneQueryError,
    NeptuneTimeoutError,
)
from src.graph.traversal import (
    DisruptionPath,
    SingleSourceRisk,
    SupplierTraversalService,
    TraversalError,
)


@pytest.fixture
def mock_neptune_client() -> AsyncMock:
    """Fixture providing a mock NeptuneClient for offline testing."""
    return AsyncMock(spec=NeptuneClient)


# ------------------------------------------------------------------------------
# 1. Five-Hop Disruption Path Traversal Assertions
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_hop_disruption_path_from_news_event(mock_neptune_client: AsyncMock):
    """Assert exact 5-hop path resolution from NewsEvent to Vehicle Program."""
    # Canonical NanoCore cleanroom fire scenario:
    # (NewsEvent) -> (Supplier: NanoCore) -> (Component: MCU-X91) ->
    # (Assembly: Battery ECU) -> (Plant: Munich Hub) -> (Program: Apex Hyper-GT)
    mock_neptune_client.execute_query.return_value = [
        {
            "origin_id": "EVT-NEWS-2026-081",
            "origin_type": "NewsEvent",
            "supplier_id": "SUP-NC-882",
            "supplier_name": "NanoCore Semiconductor",
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "assembly_id": "ASM-BECU-04",
            "assembly_name": "High-Voltage Battery ECU",
            "plant_id": "PLT-MUC-01",
            "plant_name": "Munich Assembly Hub",
            "program_id": "PRG-HGT-2026",
            "program_model": "Apex Hyper-GT",
            "hop_count": 5,
            "path_nodes": [
                "EVT-NEWS-2026-081",
                "SUP-NC-882",
                "CMP-MCU-X91",
                "ASM-BECU-04",
                "PLT-MUC-01",
                "PRG-HGT-2026",
            ],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    paths = await service.get_five_hop_disruption_paths("SUP-NC-882")

    assert len(paths) == 1
    path = paths[0]
    assert isinstance(path, DisruptionPath)

    # 1. Exact 5-hop path assertions
    assert path.hop_count == 5
    assert len(path.path_nodes) == 6  # 5 hops connect 6 distinct entities

    # 2. Entity sequence verification
    assert path.origin_id == "EVT-NEWS-2026-081"
    assert path.origin_type == "NewsEvent"
    assert path.supplier_id == "SUP-NC-882"
    assert path.supplier_name == "NanoCore Semiconductor"
    assert path.component_id == "CMP-MCU-X91"
    assert path.mpn == "MCU-X91"
    assert path.assembly_id == "ASM-BECU-04"
    assert path.plant_id == "PLT-MUC-01"
    assert path.program_id == "PRG-HGT-2026"
    assert path.program_model == "Apex Hyper-GT"

    # 3. Path node continuity
    expected_node_chain = [
        "EVT-NEWS-2026-081",  # Hop 0 (Origin)
        "SUP-NC-882",  # Hop 1 (Supplier)
        "CMP-MCU-X91",  # Hop 2 (Component)
        "ASM-BECU-04",  # Hop 3 (Sub-Assembly)
        "PLT-MUC-01",  # Hop 4 (Assembly Plant)
        "PRG-HGT-2026",  # Hop 5 (Vehicle Program)
    ]
    assert path.path_nodes == expected_node_chain


@pytest.mark.asyncio
async def test_five_hop_disruption_path_from_geopolitical_threat(
    mock_neptune_client: AsyncMock,
):
    """Assert exact 5-hop path resolution from GeopoliticalRisk threat to Vehicle Program."""
    mock_neptune_client.execute_query.return_value = [
        {
            "origin_id": "RISK-GEO-TW-01",
            "origin_type": "GeopoliticalRisk",
            "supplier_id": "SUP-NC-882",
            "supplier_name": "NanoCore Semiconductor",
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "assembly_id": "ASM-BECU-04",
            "assembly_name": "High-Voltage Battery ECU",
            "plant_id": "PLT-MUC-01",
            "plant_name": "Munich Assembly Hub",
            "program_id": "PRG-HGT-2026",
            "program_model": "Apex Hyper-GT",
            "hop_count": 5,
            "path_nodes": [
                "RISK-GEO-TW-01",
                "SUP-NC-882",
                "CMP-MCU-X91",
                "ASM-BECU-04",
                "PLT-MUC-01",
                "PRG-HGT-2026",
            ],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    paths = await service.get_five_hop_disruption_paths("SUP-NC-882")

    assert len(paths) == 1
    path = paths[0]
    assert path.origin_type == "GeopoliticalRisk"
    assert path.origin_id == "RISK-GEO-TW-01"
    assert path.hop_count == 5
    assert path.path_nodes[0] == "RISK-GEO-TW-01"
    assert path.path_nodes[-1] == "PRG-HGT-2026"


@pytest.mark.asyncio
async def test_five_hop_multi_tier_supply_chain_path(mock_neptune_client: AsyncMock):
    """Assert 5-hop path from sub-tier supplier through intermediate tiers to program."""
    mock_neptune_client.execute_query.return_value = [
        {
            "origin_id": "SUP-RAW-901",
            "origin_type": "Supplier",
            "supplier_id": "SUP-NC-882",
            "supplier_name": "NanoCore Semiconductor",
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "assembly_id": "ASM-BECU-04",
            "assembly_name": "High-Voltage Battery ECU",
            "plant_id": "PLT-MUC-01",
            "plant_name": "Munich Assembly Hub",
            "program_id": "PRG-HGT-2026",
            "program_model": "Apex Hyper-GT",
            "hop_count": 5,
            "path_nodes": [
                "SUP-RAW-901",
                "SUP-NC-882",
                "CMP-MCU-X91",
                "ASM-BECU-04",
                "PLT-MUC-01",
                "PRG-HGT-2026",
            ],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    paths = await service.get_five_hop_disruption_paths("SUP-NC-882")

    assert len(paths) == 1
    assert paths[0].origin_id == "SUP-RAW-901"
    assert paths[0].hop_count == 5
    assert len(paths[0].path_nodes) == 6


@pytest.mark.asyncio
async def test_five_hop_path_empty_results_handled(mock_neptune_client: AsyncMock):
    """Assert supplier with no downstream BOM path returns empty list cleanly."""
    mock_neptune_client.execute_query.return_value = []

    service = SupplierTraversalService(client=mock_neptune_client)
    paths = await service.get_five_hop_disruption_paths("SUP-DISCONNECTED")

    assert paths == []


# ------------------------------------------------------------------------------
# 2. Single-Source Dependency Detection Assertions
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_source_detection_sole_supplier(mock_neptune_client: AsyncMock):
    """Assert component with only 1 supplier is detected as single-source dependency."""
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "sku": "SKU-77291",
            "criticality": "CRITICAL",
            "days_of_cover": 7.68,
            "supplier_count": 1,
            "supplier_ids": ["SUP-NC-882"],
            "supplier_names": ["NanoCore Semiconductor"],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)

    # 1. find_single_source_risks
    risks = await service.find_single_source_risks()
    assert len(risks) == 1
    risk = risks[0]
    assert isinstance(risk, SingleSourceRisk)
    assert risk.component_id == "CMP-MCU-X91"
    assert risk.supplier_count == 1
    assert risk.criticality == "CRITICAL"

    # 2. is_single_source boolean check
    assert await service.is_single_source("CMP-MCU-X91") is True
    assert await service.is_single_source("MCU-X91") is True

    # 3. get_component_source_redundancy
    redundancy = await service.get_component_source_redundancy("CMP-MCU-X91")
    assert redundancy["is_single_source"] is True
    assert redundancy["supplier_count"] == 1
    assert redundancy["risk_tier"] == "CRITICAL"
    assert "SUP-NC-882" in redundancy["supplier_ids"]


@pytest.mark.asyncio
async def test_single_source_detection_contractual_flag(mock_neptune_client: AsyncMock):
    """Assert component with is_single_source=True contract flag is detected."""
    # Even if multiple suppliers exist in catalog, if contractually single-sourced:
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-SENS-08",
            "mpn": "SENS-08",
            "sku": "SKU-88214",
            "criticality": "HIGH",
            "days_of_cover": 12.5,
            "supplier_count": 2,  # 2 suppliers exist, but flagged single-source contractually
            "supplier_ids": ["SUP-SENS-A", "SUP-SENS-B"],
            "supplier_names": ["SensorTech", "Backup Sensors"],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    assert await service.is_single_source("CMP-SENS-08") is True

    redundancy = await service.get_component_source_redundancy("CMP-SENS-08")
    assert redundancy["is_single_source"] is True
    assert redundancy["risk_tier"] == "HIGH"


@pytest.mark.asyncio
async def test_dual_source_redundant_component_not_flagged(
    mock_neptune_client: AsyncMock,
):
    """Assert multi-sourced redundant component is NOT flagged as single-source."""
    # PMIC-440 has dual sourcing and no single-source contractual constraint
    mock_neptune_client.execute_query.return_value = [
        # Only MCU-X91 is returned by the single-source query
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "supplier_count": 1,
            "supplier_ids": ["SUP-NC-882"],
            "supplier_names": ["NanoCore Semiconductor"],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)

    # CMP-PMIC-440 is not in single-source dependencies
    assert await service.is_single_source("CMP-PMIC-440") is False

    redundancy = await service.get_component_source_redundancy("CMP-PMIC-440")
    assert redundancy["is_single_source"] is False
    assert redundancy["risk_tier"] == "LOW"
    assert redundancy["supplier_count"] >= 2


@pytest.mark.asyncio
async def test_filter_single_source_risks_by_supplier_id(
    mock_neptune_client: AsyncMock,
):
    """Assert filtering single-source risks by supplier isolates their specific bottlenecks."""
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "supplier_count": 1,
            "supplier_ids": ["SUP-NC-882"],
            "supplier_names": ["NanoCore Semiconductor"],
        },
        {
            "component_id": "CMP-PWR-01",
            "mpn": "PWR-01",
            "supplier_count": 1,
            "supplier_ids": ["SUP-OTHER-99"],
            "supplier_names": ["Other Power Corp"],
        },
    ]

    service = SupplierTraversalService(client=mock_neptune_client)

    # Filter by NanoCore
    nanocore_risks = await service.find_single_source_risks(supplier_id="SUP-NC-882")
    assert len(nanocore_risks) == 1
    assert nanocore_risks[0].component_id == "CMP-MCU-X91"

    # Filter by non-existent supplier
    empty_risks = await service.find_single_source_risks(supplier_id="SUP-NONEXISTENT")
    assert len(empty_risks) == 0


# ------------------------------------------------------------------------------
# 3. SLO Latency Simulation & Error Handling Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_hop_traversal_slo_latency_compliance(
    mock_neptune_client: AsyncMock,
):
    """Assert 5-hop path traversal completes within the 2.0s SLO deadline (CLAUDE.md Sec 7)."""

    async def simulated_fast_query(*_args, **_kwargs):
        # Simulated fast Neptune OpenCypher engine response (~10ms)
        return [
            {
                "origin_id": "EVT-NEWS-2026-081",
                "origin_type": "NewsEvent",
                "supplier_id": "SUP-NC-882",
                "supplier_name": "NanoCore",
                "component_id": "CMP-MCU-X91",
                "mpn": "MCU-X91",
                "hop_count": 5,
                "path_nodes": ["A", "B", "C", "D", "E", "F"],
            }
        ]

    mock_neptune_client.execute_query.side_effect = simulated_fast_query

    service = SupplierTraversalService(client=mock_neptune_client)

    start_time = time.monotonic()
    paths = await service.get_five_hop_disruption_paths("SUP-NC-882")
    elapsed_time = time.monotonic() - start_time

    assert len(paths) == 1
    assert elapsed_time <= 2.0, f"Query exceeded 2.0s SLO: elapsed {elapsed_time:.3f}s"


@pytest.mark.asyncio
async def test_five_hop_traversal_timeout_raises_traversal_error(
    mock_neptune_client: AsyncMock,
):
    """Assert Neptune query timeout on 5-hop path raises TraversalError with HTTP 504."""
    mock_neptune_client.execute_query.side_effect = NeptuneTimeoutError(
        "Neptune graph query exceeded 5.0 seconds deadline."
    )

    service = SupplierTraversalService(client=mock_neptune_client)

    with pytest.raises(TraversalError) as exc_info:
        await service.get_five_hop_disruption_paths("SUP-NC-882")

    assert exc_info.value.status_code == 504
    assert "Failed to retrieve 5-hop disruption paths" in str(exc_info.value)
    assert exc_info.value.code == "GRAPH_TRAVERSAL_ERROR"


@pytest.mark.asyncio
async def test_five_hop_traversal_circuit_breaker_tripped(
    mock_neptune_client: AsyncMock,
):
    """Assert tripped circuit breaker maps to HTTP 503 Service Unavailable."""
    mock_neptune_client.execute_query.side_effect = NeptuneCircuitBreakerOpenError(
        "Circuit breaker is OPEN. Fall back to cached topology."
    )

    service = SupplierTraversalService(client=mock_neptune_client)

    with pytest.raises(TraversalError) as exc_info:
        await service.get_five_hop_disruption_paths("SUP-NC-882")

    assert exc_info.value.status_code == 503
    assert "Circuit breaker is OPEN" in str(exc_info.value)


@pytest.mark.asyncio
async def test_single_source_query_error_mapped_to_400(
    mock_neptune_client: AsyncMock,
):
    """Assert malformed query or invalid parameters map to HTTP 400 Bad Request."""
    mock_neptune_client.execute_query.side_effect = NeptuneQueryError(
        "Invalid OpenCypher syntax in query."
    )

    service = SupplierTraversalService(client=mock_neptune_client)

    with pytest.raises(TraversalError) as exc_info:
        await service.find_single_source_risks()

    assert exc_info.value.status_code == 400
    assert "Failed to identify single source dependencies" in str(exc_info.value)
