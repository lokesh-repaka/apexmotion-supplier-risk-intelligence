"""Unit tests for Named Cypher Query Library (P5-3).

Verifies:
- Registration of mandatory named queries:
  - supplier-to-component
  - component-to-plant
  - tier-chain traversal
  - disruption blast radius
  - single-source dependency detection
  - geopolitical risk exposure
  - supplier subgraph extraction
  - external event to suppliers
  - plant to program allocations
- OpenCypher syntax keywords, labels, and relationships.
- Parameter validation and binding to prevent injection.
- Execution via NeptuneClient with offline mocking.
- NanoCore golden scenario query generation and validation.
"""

from unittest.mock import AsyncMock

import pytest
from src.graph.neptune_client import NeptuneClient
from src.graph.queries import (
    CYPHER_QUERIES,
    CypherQuery,
    CypherQueryLibrary,
    get_query,
)


def test_mandatory_named_queries_registered():
    """Verify all mandatory query names are registered in the query library."""
    mandatory_query_names = {
        "supplier_to_components",
        "component_to_plants",
        "tier_chain_traversal",
        "disruption_blast_radius",
        "single_source_dependencies",
        "geopolitical_risk_exposure",
        "supplier_subgraph",
        "event_to_suppliers",
        "plant_to_programs",
    }
    for q_name in mandatory_query_names:
        assert q_name in CYPHER_QUERIES, f"Named query '{q_name}' missing from library"
        query = get_query(q_name)
        assert isinstance(query, CypherQuery)
        assert query.name == q_name
        assert len(query.statement.strip()) > 0
        assert "MATCH" in query.statement
        assert "RETURN" in query.statement


def test_supplier_to_components_query_structure():
    """Verify supplier_to_components query parameters and labels."""
    query = get_query("supplier_to_components")
    assert "supplier_id" in query.required_parameters
    assert ":Supplier" in query.statement
    assert ":Component" in query.statement
    assert "SUPPLIES" in query.statement

    # Building query with valid parameter
    cql, params = query.build({"supplier_id": "SUP-NC-882"})
    assert "$supplier_id" in cql
    assert params["supplier_id"] == "SUP-NC-882"

    # Missing parameter raises ValueError
    with pytest.raises(ValueError) as exc_info:
        query.build({})
    assert "Missing required parameter 'supplier_id'" in str(exc_info.value)


def test_component_to_plants_query_structure():
    """Verify component_to_plants query covers direct and assembly BOM paths."""
    query = get_query("component_to_plants")
    assert "component_id" in query.required_parameters
    assert ":Component" in query.statement
    assert ":Plant" in query.statement
    assert "USED_BY" in query.statement or "PART_OF_BOM" in query.statement

    cql, params = query.build({"component_id": "CMP-MCU-X91"})
    assert "$component_id" in cql
    assert params["component_id"] == "CMP-MCU-X91"


def test_tier_chain_traversal_query_structure():
    """Verify tier_chain_traversal query uses TIER_1_OF variable-length path."""
    query = get_query("tier_chain_traversal")
    assert "supplier_id" in query.required_parameters
    assert "TIER_1_OF" in query.statement
    assert "*1.." in query.statement or "*0.." in query.statement or "*" in query.statement

    cql, params = query.build({"supplier_id": "SUP-NC-882", "max_depth": 3})
    assert "$supplier_id" in cql
    assert params["supplier_id"] == "SUP-NC-882"


def test_disruption_blast_radius_query_structure():
    """Verify disruption_blast_radius traverses multi-hop impact from supplier to plant."""
    query = get_query("disruption_blast_radius")
    assert "supplier_id" in query.required_parameters
    assert ":Supplier" in query.statement
    assert ":Component" in query.statement
    assert ":Plant" in query.statement

    cql, params = query.build({"supplier_id": "SUP-NC-882"})
    assert "$supplier_id" in cql
    assert params["supplier_id"] == "SUP-NC-882"


def test_single_source_dependencies_query_structure():
    """Verify single_source_dependencies query checks single source flags or degrees."""
    query = get_query("single_source_dependencies")
    assert ":Component" in query.statement
    assert ":Supplier" in query.statement
    # May have optional filter parameter
    cql, params = query.build()
    assert len(cql) > 0


def test_geopolitical_risk_exposure_query_structure():
    """Verify geopolitical_risk_exposure query correlates suppliers and geopolitical risks."""
    query = get_query("geopolitical_risk_exposure")
    assert ":GeopoliticalRisk" in query.statement or "THREATENS" in query.statement
    assert "risk_id" in query.optional_parameters or "supplier_id" in query.optional_parameters
    cql, params = query.build({"risk_id": "RISK-GEO-TW-01"})
    assert params["risk_id"] == "RISK-GEO-TW-01"


def test_supplier_subgraph_query_structure():
    """Verify supplier_subgraph query extracts ego-graph nodes and relationships."""
    query = get_query("supplier_subgraph")
    assert "supplier_id" in query.required_parameters
    assert "$supplier_id" in query.statement


def test_unknown_query_raises_key_error():
    """Verify attempting to get an unknown query raises KeyError."""
    with pytest.raises(KeyError) as exc_info:
        get_query("non_existent_query")
    assert "non_existent_query" in str(exc_info.value)


@pytest.mark.asyncio
async def test_library_execute_success():
    """Verify CypherQueryLibrary.execute executes query via NeptuneClient."""
    mock_client = AsyncMock(spec=NeptuneClient)
    mock_client.execute_query.return_value = [{"component_id": "CMP-MCU-X91", "sku": "SKU-77291"}]

    library = CypherQueryLibrary()
    results = await library.execute(
        client=mock_client,
        query_name="supplier_to_components",
        parameters={"supplier_id": "SUP-NC-882"},
    )

    assert len(results) == 1
    assert results[0]["component_id"] == "CMP-MCU-X91"
    mock_client.execute_query.assert_called_once()
    call_args = mock_client.execute_query.call_args
    assert "$supplier_id" in call_args[0][0]
    assert call_args[1]["parameters"] == {"supplier_id": "SUP-NC-882"}


@pytest.mark.asyncio
async def test_library_execute_missing_parameter_raises_value_error():
    """Verify CypherQueryLibrary.execute raises ValueError when required parameter missing."""
    mock_client = AsyncMock(spec=NeptuneClient)
    library = CypherQueryLibrary()

    with pytest.raises(ValueError):
        await library.execute(
            client=mock_client,
            query_name="supplier_to_components",
            parameters={},  # Missing supplier_id
        )
    mock_client.execute_query.assert_not_called()


def test_event_to_suppliers_and_plant_to_programs_query_structure():
    """Verify event_to_suppliers and plant_to_programs queries."""
    ev_query = get_query("event_to_suppliers")
    assert "event_id" in ev_query.required_parameters
    cql, params = ev_query.build({"event_id": "EVT-NEWS-2026-081"})
    assert "$event_id" in cql
    assert params["event_id"] == "EVT-NEWS-2026-081"

    plt_query = get_query("plant_to_programs")
    assert "plant_id" in plt_query.required_parameters
    cql, params = plt_query.build({"plant_id": "PLT-MUC-01"})
    assert "$plant_id" in cql
    assert params["plant_id"] == "PLT-MUC-01"


def test_library_list_queries():
    """Verify CypherQueryLibrary.list_queries returns all registered queries."""
    library = CypherQueryLibrary()
    queries = library.list_queries()
    assert len(queries) == len(CYPHER_QUERIES)
    names = {q.name for q in queries}
    assert "supplier_to_components" in names
    assert "tier_chain_traversal" in names
