"""Unit tests for Supplier Traversal Service (P5-4).

Verifies:
- Disruption blast radius traversal: Supplier -> Affected SKUs -> Consuming Plants -> Vehicle Programs.
- Canonical NanoCore golden scenario blast radius resolution (SUP-NC-882 -> MCU-X91 -> PLT-MUC-01).
- Direct and BOM-based affected plants traversal.
- Multi-tier chain traversal (Tier-2 NanoCore to Tier-1 BetaElectro).
- Single-source dependency detection and risk identification.
- Geopolitical risk correlation.
- Ego-subgraph extraction for frontend visualization.
- Resilient error handling raising TraversalError on Neptune failures.
- Offline isolation with zero external network I/O using mock NeptuneClient.
"""

from unittest.mock import AsyncMock

import pytest
from src.graph.neptune_client import NeptuneClient, NeptuneTimeoutError
from src.graph.traversal import (
    AffectedComponent,
    AffectedPlant,
    DisruptionBlastRadius,
    SingleSourceRisk,
    SupplierSubgraph,
    SupplierTraversalService,
    TierChain,
    TraversalError,
)


@pytest.fixture
def mock_neptune_client() -> AsyncMock:
    """Fixture providing a mock NeptuneClient."""
    return AsyncMock(spec=NeptuneClient)


@pytest.mark.asyncio
async def test_get_disruption_blast_radius_nanocore_golden(mock_neptune_client: AsyncMock):
    """Verify disruption blast radius for canonical NanoCore reference scenario (SUP-NC-882)."""
    # Mock response for blast radius query
    mock_neptune_client.execute_query.side_effect = [
        # 1. disruption_blast_radius
        [
            {
                "supplier_id": "SUP-NC-882",
                "supplier_name": "NanoCore Semiconductor",
                "supplier_risk_score": 0.88,
                "component_id": "CMP-MCU-X91",
                "mpn": "MCU-X91",
                "component_criticality": "CRITICAL",
                "days_of_cover": 7.68,
                "plant_id": "PLT-MUC-01",
                "plant_name": "Munich Assembly Hub",
                "hourly_downtime_rate_usd": 92000.0,
                "plant_rate_eur": 85000.0,
                "program_id": "PRG-HGT-2026",
                "program_model": "Apex Hyper-GT",
            }
        ],
        # 2. tier_chain_traversal
        [
            {
                "sub_tier_id": "SUP-NC-882",
                "sub_tier_name": "NanoCore Semiconductor",
                "sub_tier_level": 2,
                "tier_1_id": "SUP-BE-101",
                "tier_1_name": "BetaElectro AG",
                "tier_1_level": 1,
                "chain_depth": 1,
                "supplier_chain": ["SUP-NC-882", "SUP-BE-101"],
            }
        ],
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    blast_radius = await service.get_disruption_blast_radius("SUP-NC-882")

    assert isinstance(blast_radius, DisruptionBlastRadius)
    assert blast_radius.supplier_id == "SUP-NC-882"
    assert blast_radius.supplier_name == "NanoCore Semiconductor"
    assert blast_radius.supplier_risk_score == 0.88
    assert blast_radius.shortest_path_hops == 2  # Supplier -> Component -> Plant

    # Affected components
    assert len(blast_radius.affected_components) == 1
    comp = blast_radius.affected_components[0]
    assert comp.component_id == "CMP-MCU-X91"
    assert comp.mpn == "MCU-X91"
    assert comp.criticality == "CRITICAL"
    assert comp.days_of_cover == 7.68

    # Affected plants
    assert len(blast_radius.affected_plants) == 1
    plant = blast_radius.affected_plants[0]
    assert plant.plant_id == "PLT-MUC-01"
    assert plant.plant_name == "Munich Assembly Hub"
    assert plant.rate_eur == 85000.0

    # Affected programs
    assert len(blast_radius.affected_programs) == 1
    prog = blast_radius.affected_programs[0]
    assert prog.program_id == "PRG-HGT-2026"
    assert prog.model == "Apex Hyper-GT"

    # Tier chains
    assert len(blast_radius.tier_chains) == 1
    chain = blast_radius.tier_chains[0]
    assert chain.tier_1_id == "SUP-BE-101"
    assert chain.supplier_chain == ["SUP-NC-882", "SUP-BE-101"]


@pytest.mark.asyncio
async def test_get_affected_components(mock_neptune_client: AsyncMock):
    """Verify get_affected_components extracts domain models with single-source flags."""
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "sku": "SKU-77291",
            "description": "32-Bit MCU",
            "criticality": "CRITICAL",
            "days_of_cover": 7.68,
            "daily_consumption_rate": 18500.0,
            "relationship_type": "SUPPLIES_PART",
            "contract_id": "CTR-NC-2024-01",
            "is_single_source": True,
            "lead_time_days": 45,
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    components = await service.get_affected_components("SUP-NC-882")

    assert len(components) == 1
    comp = components[0]
    assert isinstance(comp, AffectedComponent)
    assert comp.mpn == "MCU-X91"
    assert comp.is_single_source is True
    assert comp.days_of_cover == 7.68


@pytest.mark.asyncio
async def test_get_affected_plants(mock_neptune_client: AsyncMock):
    """Verify get_affected_plants extracts unique consuming assembly facilities."""
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "plant_id": "PLT-MUC-01",
            "plant_name": "Munich Assembly Hub",
            "location": "Munich",
            "country": "DE",
            "region": "EMEA",
            "hourly_downtime_rate_usd": 92000.0,
            "rate_eur": 85000.0,
            "capacity": 500,
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    plants = await service.get_affected_plants("CMP-MCU-X91")

    assert len(plants) == 1
    plant = plants[0]
    assert isinstance(plant, AffectedPlant)
    assert plant.plant_id == "PLT-MUC-01"
    assert plant.rate_eur == 85000.0


@pytest.mark.asyncio
async def test_get_tier_chain(mock_neptune_client: AsyncMock):
    """Verify get_tier_chain retrieves multi-hop tier hierarchy."""
    mock_neptune_client.execute_query.return_value = [
        {
            "sub_tier_id": "SUP-NC-882",
            "sub_tier_name": "NanoCore Semiconductor",
            "sub_tier_level": 2,
            "tier_1_id": "SUP-BE-101",
            "tier_1_name": "BetaElectro AG",
            "tier_1_level": 1,
            "chain_depth": 1,
            "supplier_chain": ["SUP-NC-882", "SUP-BE-101"],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    chains = await service.get_tier_chain("SUP-NC-882")

    assert len(chains) == 1
    chain = chains[0]
    assert isinstance(chain, TierChain)
    assert chain.sub_tier_id == "SUP-NC-882"
    assert chain.tier_1_id == "SUP-BE-101"


@pytest.mark.asyncio
async def test_find_single_source_risks(mock_neptune_client: AsyncMock):
    """Verify find_single_source_risks identifies vulnerable single-supplier parts."""
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
    risks = await service.find_single_source_risks()

    assert len(risks) == 1
    risk = risks[0]
    assert isinstance(risk, SingleSourceRisk)
    assert risk.mpn == "MCU-X91"
    assert risk.supplier_count == 1
    assert "SUP-NC-882" in risk.supplier_ids


@pytest.mark.asyncio
async def test_get_geopolitical_exposure(mock_neptune_client: AsyncMock):
    """Verify get_geopolitical_exposure returns regional risks for a supplier."""
    mock_neptune_client.execute_query.return_value = [
        {
            "risk_id": "RISK-GEO-TW-01",
            "region": "East Asia",
            "risk_type": "EXPORT_RESTRICTION_LOGISTICS",
            "severity": "HIGH",
            "supplier_id": "SUP-NC-882",
            "supplier_name": "NanoCore Semiconductor",
            "supplier_country": "TW",
            "supplier_tier": 2,
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    exposures = await service.get_geopolitical_exposure(supplier_id="SUP-NC-882")

    assert len(exposures) == 1
    exp = exposures[0]
    assert exp.risk_id == "RISK-GEO-TW-01"
    assert exp.region == "East Asia"
    assert exp.severity == "HIGH"


@pytest.mark.asyncio
async def test_get_supplier_subgraph(mock_neptune_client: AsyncMock):
    """Verify get_supplier_subgraph constructs ego-graph nodes and edges for visualization."""
    mock_neptune_client.execute_query.return_value = [
        {
            "s": {"id": "SUP-NC-882", "name": "NanoCore"},
            "edges_hop1": [{"from": "SUP-NC-882", "to": "CMP-MCU-X91", "type": "SUPPLIES"}],
            "nodes_hop1": [{"id": "CMP-MCU-X91", "mpn": "MCU-X91"}],
            "edges_hop2": [{"from": "CMP-MCU-X91", "to": "PLT-MUC-01", "type": "USED_BY"}],
            "nodes_hop2": [{"id": "PLT-MUC-01", "name": "Munich Hub"}],
        }
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    subgraph = await service.get_supplier_subgraph("SUP-NC-882")

    assert isinstance(subgraph, SupplierSubgraph)
    assert subgraph.supplier_id == "SUP-NC-882"
    assert len(subgraph.nodes) >= 3  # Supplier + Component + Plant
    assert len(subgraph.edges) >= 2  # SUPPLIES + USED_BY


@pytest.mark.asyncio
async def test_blast_radius_empty_downstream_handled(mock_neptune_client: AsyncMock):
    """Verify empty query result handles gracefully without errors."""
    mock_neptune_client.execute_query.side_effect = [[], []]

    service = SupplierTraversalService(client=mock_neptune_client)
    blast_radius = await service.get_disruption_blast_radius("SUP-NON-EXISTENT")

    assert blast_radius.supplier_id == "SUP-NON-EXISTENT"
    assert len(blast_radius.affected_components) == 0
    assert len(blast_radius.affected_plants) == 0
    assert blast_radius.shortest_path_hops == 0


@pytest.mark.asyncio
async def test_traversal_neptune_timeout_raises_traversal_error(mock_neptune_client: AsyncMock):
    """Verify Neptune timeout raises TraversalError with contextual details."""
    mock_neptune_client.execute_query.side_effect = NeptuneTimeoutError(
        "Neptune graph query exceeded 5.0 seconds."
    )

    service = SupplierTraversalService(client=mock_neptune_client)
    with pytest.raises(TraversalError) as exc_info:
        await service.get_disruption_blast_radius("SUP-NC-882")

    assert "Failed to calculate disruption blast radius" in str(exc_info.value)
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_get_affected_plants_with_supplier_id(mock_neptune_client: AsyncMock):
    """Verify get_affected_plants delegates to blast radius when given a supplier ID."""
    mock_neptune_client.execute_query.side_effect = [
        [
            {
                "supplier_id": "SUP-NC-882",
                "supplier_name": "NanoCore",
                "plant_id": "PLT-MUC-01",
                "plant_name": "Munich Hub",
                "plant_rate_eur": 85000.0,
            }
        ],
        [],
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    plants = await service.get_affected_plants("SUP-NC-882")

    assert len(plants) == 1
    assert plants[0].plant_id == "PLT-MUC-01"


@pytest.mark.asyncio
async def test_find_single_source_risks_filter_supplier(mock_neptune_client: AsyncMock):
    """Verify find_single_source_risks correctly filters by specific supplier ID."""
    mock_neptune_client.execute_query.return_value = [
        {
            "component_id": "CMP-MCU-X91",
            "mpn": "MCU-X91",
            "supplier_ids": ["SUP-NC-882"],
            "supplier_names": ["NanoCore"],
        },
        {
            "component_id": "CMP-OTH-999",
            "mpn": "OTH-999",
            "supplier_ids": ["SUP-OTHER"],
            "supplier_names": ["Other Corp"],
        },
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    risks = await service.find_single_source_risks(supplier_id="SUP-NC-882")

    assert len(risks) == 1
    assert risks[0].component_id == "CMP-MCU-X91"


@pytest.mark.asyncio
async def test_traversal_errors_mapped_properly(mock_neptune_client: AsyncMock):
    """Verify various Neptune client errors are mapped to appropriate HTTP status codes."""
    from src.graph.neptune_client import (
        NeptuneCircuitBreakerOpenError,
        NeptuneConnectionError,
        NeptuneQueryError,
    )

    service = SupplierTraversalService(client=mock_neptune_client)

    # 1. Connection error -> 503
    mock_neptune_client.execute_query.side_effect = NeptuneConnectionError("Neptune unreachable")
    with pytest.raises(TraversalError) as exc_conn:
        await service.get_affected_components("SUP-NC-882")
    assert exc_conn.value.status_code == 503

    # 2. Circuit breaker open -> 503
    mock_neptune_client.execute_query.side_effect = NeptuneCircuitBreakerOpenError(
        "Circuit tripped"
    )
    with pytest.raises(TraversalError) as exc_cb:
        await service.get_tier_chain("SUP-NC-882")
    assert exc_cb.value.status_code == 503

    # 3. Query error -> 400
    mock_neptune_client.execute_query.side_effect = NeptuneQueryError("Syntax error")
    with pytest.raises(TraversalError) as exc_query:
        await service.find_single_source_risks()
    assert exc_query.value.status_code == 400

    # 4. Generic error -> 500
    mock_neptune_client.execute_query.side_effect = RuntimeError("Unexpected runtime failure")
    with pytest.raises(TraversalError) as exc_gen:
        await service.get_geopolitical_exposure()
    assert exc_gen.value.status_code == 500

    # 5. Subgraph error -> 500
    mock_neptune_client.execute_query.side_effect = RuntimeError("Subgraph extraction failed")
    with pytest.raises(TraversalError) as exc_sub:
        await service.get_supplier_subgraph("SUP-NC-882")
    assert exc_sub.value.status_code == 500

    # 6. Affected plants error -> 500
    mock_neptune_client.execute_query.side_effect = RuntimeError("Plants query failed")
    with pytest.raises(TraversalError) as exc_plants:
        await service.get_affected_plants("CMP-MCU-X91")
    assert exc_plants.value.status_code == 500


def test_supplier_traversal_service_default_init():
    """Verify default initialization without injected dependencies."""
    service = SupplierTraversalService()
    assert service._client is not None
    assert service._library is not None


@pytest.mark.asyncio
async def test_blast_radius_components_only_hops_is_one(mock_neptune_client: AsyncMock):
    """Verify shortest_path_hops is 1 when components exist but no plants consume them."""
    mock_neptune_client.execute_query.side_effect = [
        [
            {
                "supplier_id": "SUP-RAW-001",
                "supplier_name": "Raw Materials Corp",
                "component_id": "CMP-RAW-01",
                "mpn": "RAW-01",
                "component_criticality": "MEDIUM",
                # no plant_id
            }
        ],
        [],
    ]

    service = SupplierTraversalService(client=mock_neptune_client)
    blast = await service.get_disruption_blast_radius("SUP-RAW-001")

    assert len(blast.affected_components) == 1
    assert len(blast.affected_plants) == 0
    assert blast.shortest_path_hops == 1


@pytest.mark.asyncio
async def test_traversal_base_neptune_client_error_mapped(mock_neptune_client: AsyncMock):
    """Verify base NeptuneClientError preserves its status code."""
    from src.graph.neptune_client import NeptuneClientError

    mock_neptune_client.execute_query.side_effect = NeptuneClientError(
        message="Base client error", status_code=502
    )

    service = SupplierTraversalService(client=mock_neptune_client)
    with pytest.raises(TraversalError) as exc_info:
        await service.get_disruption_blast_radius("SUP-NC-882")

    assert exc_info.value.status_code == 502
