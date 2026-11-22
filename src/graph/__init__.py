"""Knowledge Graph package for ApexMotion platform.

Exports:
- NeptuneClient: Async Amazon Neptune OpenCypher client.
- NeptuneClientError: Base Neptune exception.
- NeptuneConnectionError: Connection or transient failure error.
- NeptuneTimeoutError: Gateway timeout (GRAPH_504_TIMEOUT).
- NeptuneQueryError: Invalid OpenCypher query or parameters.
- NeptuneCircuitBreakerOpenError: Circuit breaker tripped error.
"""

from src.graph.neptune_client import (
    NeptuneCircuitBreakerOpenError,
    NeptuneClient,
    NeptuneClientError,
    NeptuneConnectionError,
    NeptuneQueryError,
    NeptuneTimeoutError,
)

__all__ = [
    "NeptuneCircuitBreakerOpenError",
    "NeptuneClient",
    "NeptuneClientError",
    "NeptuneConnectionError",
    "NeptuneQueryError",
    "NeptuneTimeoutError",
]
