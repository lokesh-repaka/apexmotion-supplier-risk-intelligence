"""Named Cypher query library for Amazon Neptune (P5-3).

Exports:
- CypherQuery: Data model for parameterized Cypher query template.
- CypherQueryLibrary: Query catalog and execution engine.
- CYPHER_QUERIES: Dictionary registry of all named queries.
- get_query: Helper to retrieve named CypherQuery.
- Query constants for direct reference:
  - QUERY_SUPPLIER_TO_COMPONENTS
  - QUERY_COMPONENT_TO_PLANTS
  - QUERY_TIER_CHAIN_TRAVERSAL
  - QUERY_DISRUPTION_BLAST_RADIUS
  - QUERY_SINGLE_SOURCE_DEPENDENCIES
  - QUERY_GEOPOLITICAL_RISK_EXPOSURE
  - QUERY_SUPPLIER_SUBGRAPH
  - QUERY_EVENT_TO_SUPPLIERS
  - QUERY_PLANT_TO_PROGRAMS
"""

from src.graph.queries.library import (
    CYPHER_QUERIES,
    QUERY_COMPONENT_TO_PLANTS,
    QUERY_DISRUPTION_BLAST_RADIUS,
    QUERY_EVENT_TO_SUPPLIERS,
    QUERY_GEOPOLITICAL_RISK_EXPOSURE,
    QUERY_PLANT_TO_PROGRAMS,
    QUERY_SINGLE_SOURCE_DEPENDENCIES,
    QUERY_SUPPLIER_SUBGRAPH,
    QUERY_SUPPLIER_TO_COMPONENTS,
    QUERY_TIER_CHAIN_TRAVERSAL,
    CypherQuery,
    CypherQueryLibrary,
    get_query,
)

__all__ = [
    "CYPHER_QUERIES",
    "QUERY_COMPONENT_TO_PLANTS",
    "QUERY_DISRUPTION_BLAST_RADIUS",
    "QUERY_EVENT_TO_SUPPLIERS",
    "QUERY_GEOPOLITICAL_RISK_EXPOSURE",
    "QUERY_PLANT_TO_PROGRAMS",
    "QUERY_SINGLE_SOURCE_DEPENDENCIES",
    "QUERY_SUPPLIER_SUBGRAPH",
    "QUERY_SUPPLIER_TO_COMPONENTS",
    "QUERY_TIER_CHAIN_TRAVERSAL",
    "CypherQuery",
    "CypherQueryLibrary",
    "get_query",
]
