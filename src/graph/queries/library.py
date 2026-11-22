"""Named Cypher query registry and execution engine for Amazon Neptune (P5-3).

Enforces:
- Deterministic, parameterized OpenCypher query templates (zero string interpolation).
- Parameter validation guarding against Cypher injection (SEC-024).
- Standardized execution through NeptuneClient with trace propagation.
- Canonical queries for multi-tier automotive supply chain traversal.
"""

from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_logger
from src.graph.neptune_client import NeptuneClient

logger = get_logger("apexmotion.graph.queries")


@dataclass
class CypherQuery:
    """Named OpenCypher query template with parameter contracts."""

    name: str
    statement: str
    description: str
    required_parameters: list[str] = field(default_factory=list)
    optional_parameters: dict[str, Any] = field(default_factory=dict)

    def build(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Validate and construct parameterized OpenCypher query and parameter dict.

        Args:
            parameters: Dictionary of query parameters.

        Returns:
            Tuple of (query_statement, parameter_dict).

        Raises:
            ValueError: If a required parameter is missing.
        """
        params = dict(self.optional_parameters)
        if parameters:
            params.update(parameters)

        # Validate required parameters
        for req_param in self.required_parameters:
            if req_param not in params or params[req_param] is None:
                raise ValueError(
                    f"Missing required parameter '{req_param}' for query '{self.name}'"
                )

        return self.statement, params


# ------------------------------------------------------------------------------
# Core Named Cypher Query Statements (CLAUDE.md Sec 8.2 & FRD Sec 5.2)
# ------------------------------------------------------------------------------

QUERY_SUPPLIER_TO_COMPONENTS = """
MATCH (s:Supplier {id: $supplier_id})-[r:SUPPLIES|SUPPLIES_PART]->(c:Component)
RETURN s.id AS supplier_id,
       s.name AS supplier_name,
       s.tier AS supplier_tier,
       c.id AS component_id,
       c.mpn AS mpn,
       c.sku AS sku,
       c.description AS description,
       c.criticality AS criticality,
       c.days_of_cover AS days_of_cover,
       c.daily_consumption_rate AS daily_consumption_rate,
       type(r) AS relationship_type,
       r.contract_id AS contract_id,
       coalesce(r.is_single_source, false) AS is_single_source,
       coalesce(r.lead_time_days, 0) AS lead_time_days
ORDER BY c.criticality DESC, c.mpn ASC
""".strip()

QUERY_COMPONENT_TO_PLANTS = """
MATCH (c:Component {id: $component_id})
OPTIONAL MATCH (c)-[:USED_BY]->(direct_p:Plant)
OPTIONAL MATCH (c)-[b:PART_OF_BOM]->(a:Assembly)-[:ASSEMBLED_AT]->(bom_p:Plant)
WITH c,
     collect(DISTINCT direct_p) + collect(DISTINCT bom_p) AS all_plants,
     collect(DISTINCT a) AS assemblies
UNWIND all_plants AS p
RETURN c.id AS component_id,
       c.mpn AS mpn,
       p.id AS plant_id,
       p.name AS plant_name,
       p.location AS location,
       p.country AS country,
       p.region AS region,
       p.hourly_downtime_rate_usd AS hourly_downtime_rate_usd,
       p.rate_eur AS rate_eur,
       p.capacity AS capacity
ORDER BY p.name ASC
""".strip()

QUERY_TIER_CHAIN_TRAVERSAL = """
MATCH path = (sub:Supplier {id: $supplier_id})-[:TIER_1_OF*1..4]->(t1:Supplier)
RETURN sub.id AS sub_tier_id,
       sub.name AS sub_tier_name,
       sub.tier AS sub_tier_level,
       t1.id AS tier_1_id,
       t1.name AS tier_1_name,
       t1.tier AS tier_1_level,
       length(path) AS chain_depth,
       [n IN nodes(path) | n.id] AS supplier_chain
ORDER BY length(path) ASC
""".strip()

QUERY_DISRUPTION_BLAST_RADIUS = """
MATCH (s:Supplier {id: $supplier_id})
OPTIONAL MATCH (s)-[:SUPPLIES|SUPPLIES_PART]->(c:Component)
OPTIONAL MATCH (c)-[:USED_BY]->(p_direct:Plant)
OPTIONAL MATCH (c)-[:PART_OF_BOM]->(a:Assembly)-[:ASSEMBLED_AT]->(p_assy:Plant)
WITH s, c, coalesce(p_direct, p_assy) AS p
OPTIONAL MATCH (p)-[:ALLOCATED_TO]->(prg:Program)
RETURN s.id AS supplier_id,
       s.name AS supplier_name,
       s.risk_score AS supplier_risk_score,
       c.id AS component_id,
       c.mpn AS mpn,
       c.criticality AS component_criticality,
       c.days_of_cover AS days_of_cover,
       p.id AS plant_id,
       p.name AS plant_name,
       p.hourly_downtime_rate_usd AS hourly_downtime_rate_usd,
       p.rate_eur AS plant_rate_eur,
       prg.id AS program_id,
       prg.model AS program_model
ORDER BY c.days_of_cover ASC
""".strip()

QUERY_SINGLE_SOURCE_DEPENDENCIES = """
MATCH (s:Supplier)-[r:SUPPLIES|SUPPLIES_PART]->(c:Component)
WITH c, count(DISTINCT s) AS supplier_count, collect(s) AS suppliers, collect(r) AS rels
WHERE supplier_count = 1 OR any(rel IN rels WHERE rel.is_single_source = true)
RETURN c.id AS component_id,
       c.mpn AS mpn,
       c.sku AS sku,
       c.criticality AS criticality,
       c.days_of_cover AS days_of_cover,
       supplier_count,
       [sup IN suppliers | sup.id] AS supplier_ids,
       [sup IN suppliers | sup.name] AS supplier_names
ORDER BY c.days_of_cover ASC
""".strip()

QUERY_GEOPOLITICAL_RISK_EXPOSURE = """
MATCH (g:GeopoliticalRisk)
OPTIONAL MATCH (g)-[:THREATENS]->(s:Supplier)
WHERE ($risk_id IS NOT NULL AND g.id = $risk_id)
   OR ($supplier_id IS NOT NULL AND s.id = $supplier_id)
   OR ($risk_id IS NULL AND $supplier_id IS NULL)
RETURN g.id AS risk_id,
       g.region AS region,
       g.risk_type AS risk_type,
       g.severity AS severity,
       s.id AS supplier_id,
       s.name AS supplier_name,
       s.country AS supplier_country,
       s.tier AS supplier_tier
ORDER BY g.severity DESC, s.name ASC
""".strip()

QUERY_SUPPLIER_SUBGRAPH = """
MATCH (s:Supplier {id: $supplier_id})
OPTIONAL MATCH (s)-[r1]-(n1)
OPTIONAL MATCH (n1)-[r2]-(n2)
WHERE NOT n2:Supplier OR n2.id <> s.id
RETURN s,
       collect(DISTINCT {from: startNode(r1).id, to: endNode(r1).id, type: type(r1)}) AS edges_hop1,
       collect(DISTINCT n1) AS nodes_hop1,
       collect(DISTINCT {from: startNode(r2).id, to: endNode(r2).id, type: type(r2)}) AS edges_hop2,
       collect(DISTINCT n2) AS nodes_hop2
""".strip()

QUERY_EVENT_TO_SUPPLIERS = """
MATCH (ne:NewsEvent {id: $event_id})-[:AFFECTS]->(s:Supplier)
RETURN ne.id AS event_id,
       ne.headline AS headline,
       ne.sentiment AS sentiment,
       ne.source AS source,
       s.id AS supplier_id,
       s.name AS supplier_name,
       s.tier AS supplier_tier,
       s.country AS supplier_country
ORDER BY s.name ASC
""".strip()

QUERY_PLANT_TO_PROGRAMS = """
MATCH (p:Plant {id: $plant_id})-[r:ALLOCATED_TO]->(prg:Program)
RETURN p.id AS plant_id,
       p.name AS plant_name,
       prg.id AS program_id,
       prg.model AS model,
       prg.daily_target_units AS daily_target_units,
       r.daily_build_quota AS daily_build_quota,
       prg.margin_per_unit_usd AS margin_per_unit_usd
ORDER BY prg.model ASC
""".strip()

QUERY_FIVE_HOP_DISRUPTION_PATH = """
MATCH path = (origin)-[:AFFECTS|THREATENS|TIER_1_OF]->(s:Supplier {id: $supplier_id})-[:SUPPLIES|SUPPLIES_PART]->(c:Component)-[:PART_OF_BOM]->(a:Assembly)-[:ASSEMBLED_AT]->(p:Plant)-[:ALLOCATED_TO]->(prg:Program)
RETURN coalesce(origin.id, id(origin)) AS origin_id,
       labels(origin)[0] AS origin_type,
       s.id AS supplier_id,
       s.name AS supplier_name,
       c.id AS component_id,
       c.mpn AS mpn,
       a.id AS assembly_id,
       a.name AS assembly_name,
       p.id AS plant_id,
       p.name AS plant_name,
       prg.id AS program_id,
       prg.model AS program_model,
       length(path) AS hop_count,
       [n IN nodes(path) | coalesce(n.id, id(n))] AS path_nodes
ORDER BY length(path) ASC
""".strip()


# ------------------------------------------------------------------------------
# Query Registry & Library Engine
# ------------------------------------------------------------------------------

CYPHER_QUERIES: dict[str, CypherQuery] = {
    "supplier_to_components": CypherQuery(
        name="supplier_to_components",
        statement=QUERY_SUPPLIER_TO_COMPONENTS,
        description="Retrieve all components directly supplied by a supplier with criticality and lead time.",
        required_parameters=["supplier_id"],
    ),
    "component_to_plants": CypherQuery(
        name="component_to_plants",
        statement=QUERY_COMPONENT_TO_PLANTS,
        description="Retrieve all assembly plants consuming a component directly or via sub-assembly BOM.",
        required_parameters=["component_id"],
    ),
    "tier_chain_traversal": CypherQuery(
        name="tier_chain_traversal",
        statement=QUERY_TIER_CHAIN_TRAVERSAL,
        description="Traverse multi-hop TIER_1_OF relationships from sub-tier supplier to Tier-1 suppliers.",
        required_parameters=["supplier_id"],
        optional_parameters={"max_depth": 4},
    ),
    "disruption_blast_radius": CypherQuery(
        name="disruption_blast_radius",
        statement=QUERY_DISRUPTION_BLAST_RADIUS,
        description="Traverse multi-hop impact from disrupted supplier across components, plants, and programs.",
        required_parameters=["supplier_id"],
    ),
    "single_source_dependencies": CypherQuery(
        name="single_source_dependencies",
        statement=QUERY_SINGLE_SOURCE_DEPENDENCIES,
        description="Identify components that depend on a single supplier or have is_single_source=true.",
    ),
    "geopolitical_risk_exposure": CypherQuery(
        name="geopolitical_risk_exposure",
        statement=QUERY_GEOPOLITICAL_RISK_EXPOSURE,
        description="Identify suppliers exposed to specific geopolitical risks or sharing regional threat exposure.",
        optional_parameters={"risk_id": None, "supplier_id": None},
    ),
    "supplier_subgraph": CypherQuery(
        name="supplier_subgraph",
        statement=QUERY_SUPPLIER_SUBGRAPH,
        description="Extract 2-hop ego-graph around a supplier for graph visualization.",
        required_parameters=["supplier_id"],
    ),
    "event_to_suppliers": CypherQuery(
        name="event_to_suppliers",
        statement=QUERY_EVENT_TO_SUPPLIERS,
        description="Identify suppliers directly affected by external incidents and news events.",
        required_parameters=["event_id"],
    ),
    "plant_to_programs": CypherQuery(
        name="plant_to_programs",
        statement=QUERY_PLANT_TO_PROGRAMS,
        description="Retrieve vehicle model programs and capacity allocations for an assembly plant.",
        required_parameters=["plant_id"],
    ),
    "five_hop_disruption_path": CypherQuery(
        name="five_hop_disruption_path",
        statement=QUERY_FIVE_HOP_DISRUPTION_PATH,
        description="Traverse 5-hop disruption path: External Threat/Incident -> Supplier -> Component -> Assembly -> Plant -> Program.",
        required_parameters=["supplier_id"],
    ),
}


def get_query(name: str) -> CypherQuery:
    """Retrieve named CypherQuery from registry.

    Args:
        name: Query registry identifier.

    Returns:
        CypherQuery instance.

    Raises:
        KeyError: If query name is not registered.
    """
    if name not in CYPHER_QUERIES:
        raise KeyError(
            f"Named Cypher query '{name}' not found. Available queries: {list(CYPHER_QUERIES.keys())}"
        )
    return CYPHER_QUERIES[name]


class CypherQueryLibrary:
    """Registry and execution facade for named Neptune OpenCypher queries."""

    def __init__(self) -> None:
        self._queries = dict(CYPHER_QUERIES)

    def get(self, name: str) -> CypherQuery:
        """Get named query from library."""
        return get_query(name)

    def list_queries(self) -> list[CypherQuery]:
        """List all registered Cypher queries."""
        return list(self._queries.values())

    async def execute(
        self,
        client: NeptuneClient,
        query_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build and execute a named Cypher query against Amazon Neptune.

        Args:
            client: Active NeptuneClient instance.
            query_name: Registered query name.
            parameters: Optional query parameter bindings.

        Returns:
            List of record dictionaries from Neptune JSON response.

        Raises:
            KeyError: If query_name is not registered.
            ValueError: If a required parameter is missing.
            NeptuneClientError: If query execution fails.
        """
        query = self.get(query_name)
        cql, bound_params = query.build(parameters)
        logger.debug(
            "Executing named query '%s' with parameters: %s",
            query_name,
            list(bound_params.keys()),
        )
        return await client.execute_query(cql, parameters=bound_params)
