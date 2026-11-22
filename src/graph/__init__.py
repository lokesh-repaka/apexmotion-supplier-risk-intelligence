"""Knowledge Graph package for ApexMotion platform.

Exports:
- NeptuneClient: Async Amazon Neptune OpenCypher client.
- NeptuneClientError: Base Neptune exception.
- NeptuneConnectionError: Connection or transient failure error.
- NeptuneTimeoutError: Gateway timeout (GRAPH_504_TIMEOUT).
- NeptuneQueryError: Invalid OpenCypher query or parameters.
- NeptuneCircuitBreakerOpenError: Circuit breaker tripped error.
- GraphSeedError: Seed or verification execution failure.
- SeedResult: Seeding outcome metrics.
- seed_graph: Seeding execution function.
- verify_seed_integrity: Post-seeding validation report.
- get_seed_cypher_statements: Statement generator.
- CypherQuery: Parameterized Cypher query container.
- CypherQueryLibrary: Query catalog and executor.
- CYPHER_QUERIES: Named query dictionary.
- get_query: Helper to get query by name.
"""

from src.graph.neptune_client import (
    NeptuneCircuitBreakerOpenError,
    NeptuneClient,
    NeptuneClientError,
    NeptuneConnectionError,
    NeptuneQueryError,
    NeptuneTimeoutError,
)
from src.graph.queries import (
    CYPHER_QUERIES,
    CypherQuery,
    CypherQueryLibrary,
    get_query,
)
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

__all__ = [
    "CYPHER_QUERIES",
    "GOLDEN_COMPONENTS",
    "GOLDEN_CONTRACTS",
    "GOLDEN_EXTERNAL_SIGNALS",
    "GOLDEN_PLANTS",
    "GOLDEN_RELATIONSHIPS",
    "GOLDEN_SUPPLIERS",
    "CypherQuery",
    "CypherQueryLibrary",
    "GraphSeedError",
    "NeptuneCircuitBreakerOpenError",
    "NeptuneClient",
    "NeptuneClientError",
    "NeptuneConnectionError",
    "NeptuneQueryError",
    "NeptuneTimeoutError",
    "SeedResult",
    "get_query",
    "get_seed_cypher_statements",
    "seed_graph",
    "verify_seed_integrity",
]
