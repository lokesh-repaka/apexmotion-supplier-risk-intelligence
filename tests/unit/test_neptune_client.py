"""Unit tests for Neptune OpenCypher client (P5-1).

Verifies:
- NeptuneClient initialization with default and custom configurations.
- Execution of OpenCypher queries via POST /openCypher with parameters.
- Parsing of OpenCypher JSON results.
- Trace ID propagation in request headers.
- Exponential backoff retry logic on transient HTTP status codes (429, 500, 502, 503, 504).
- Immediate failure without retry on client error (400 Bad Request).
- Timeout handling raising NeptuneTimeoutError (GRAPH_504_TIMEOUT).
- Circuit breaker tripping after consecutive timeouts/failures.
- Async context manager lifecycle (closing connection pool).
- Health check probe execution.
"""

import httpx
import pytest
from src.core.logging import bind_trace_id
from src.graph.neptune_client import (
    NeptuneCircuitBreakerOpenError,
    NeptuneClient,
    NeptuneClientError,
    NeptuneConnectionError,
    NeptuneQueryError,
    NeptuneTimeoutError,
)


@pytest.mark.asyncio
async def test_neptune_client_initialization_defaults():
    """Verify default client initialization parameters and base URL construction."""
    client = NeptuneClient()
    assert client.endpoint == "localhost"
    assert client.port == 8182
    assert not client.use_ssl
    assert client.base_url == "http://localhost:8182"
    assert client.timeout == 5.0
    assert client.max_retries == 3
    assert client.initial_backoff == 0.5
    assert not client.is_circuit_open
    await client.close()


@pytest.mark.asyncio
async def test_neptune_client_initialization_custom():
    """Verify custom client initialization parameters."""
    client = NeptuneClient(
        endpoint="neptune.eu-central-1.neptune.amazonaws.com",
        port=8182,
        use_ssl=True,
        timeout=10.0,
        max_retries=2,
        initial_backoff=0.2,
        circuit_breaker_threshold=3,
    )
    assert client.endpoint == "neptune.eu-central-1.neptune.amazonaws.com"
    assert client.port == 8182
    assert client.use_ssl
    assert client.base_url == "https://neptune.eu-central-1.neptune.amazonaws.com:8182"
    assert client.timeout == 10.0
    assert client.max_retries == 2
    assert client.initial_backoff == 0.2
    assert client.circuit_breaker_threshold == 3
    await client.close()


@pytest.mark.asyncio
async def test_execute_query_success():
    """Verify successful query execution and result extraction."""
    mock_results = [
        {"s.id": "SUP-NC-882", "s.name": "NanoCore Semiconductor"},
        {"s.id": "SUP-BE-101", "s.name": "BetaElectro AG"},
    ]
    query = "MATCH (s:Supplier) RETURN s.id, s.name"
    params = {"tier": 2}

    def custom_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/openCypher"
        import json

        body = json.loads(request.content.decode("utf-8"))
        assert body["query"] == query
        assert body["parameters"] == params
        assert request.headers["x-trace-id"] == "test-trace-123"
        return httpx.Response(
            status_code=200,
            json={"results": mock_results},
        )

    transport = httpx.MockTransport(custom_handler)
    async with NeptuneClient(transport=transport) as client:
        with bind_trace_id("test-trace-123"):
            results = await client.execute_query(query, parameters=params)

    assert results == mock_results
    assert client.consecutive_failures == 0


@pytest.mark.asyncio
async def test_execute_query_empty_results():
    """Verify query with no matched results returns empty list."""
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(status_code=200, json={"results": []})
    )
    async with NeptuneClient(transport=transport) as client:
        results = await client.execute_query("MATCH (n:NonExistent) RETURN n")
        assert results == []


@pytest.mark.asyncio
async def test_execute_query_transient_retry_success():
    """Verify transient failures (503, 429) trigger backoff and eventual success."""
    call_count = 0

    def retry_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(status_code=503, text="Service Unavailable")
        elif call_count == 2:
            return httpx.Response(status_code=429, text="Too Many Requests")
        return httpx.Response(
            status_code=200,
            json={"results": [{"id": "SUP-NC-882"}]},
        )

    transport = httpx.MockTransport(retry_handler)
    async with NeptuneClient(transport=transport, initial_backoff=0.01) as client:
        results = await client.execute_query("MATCH (s:Supplier) RETURN s.id")

    assert len(results) == 1
    assert results[0]["id"] == "SUP-NC-882"
    assert call_count == 3
    assert client.consecutive_failures == 0


@pytest.mark.asyncio
async def test_execute_query_max_retries_exceeded():
    """Verify exceeding max retries on 503 raises NeptuneConnectionError."""
    call_count = 0

    def fail_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=503, text="Service Unavailable")

    transport = httpx.MockTransport(fail_handler)
    async with NeptuneClient(transport=transport, max_retries=2, initial_backoff=0.01) as client:
        with pytest.raises(NeptuneConnectionError) as exc_info:
            await client.execute_query("MATCH (s:Supplier) RETURN s")

        assert "Max retries (2) exceeded" in str(exc_info.value)
        assert call_count == 3  # initial + 2 retries
        assert client.consecutive_failures == 1


@pytest.mark.asyncio
async def test_execute_query_bad_request_fails_immediately():
    """Verify 400 Bad Request raises NeptuneQueryError without retry."""
    call_count = 0

    def bad_request_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=400,
            json={
                "code": "InvalidParameterException",
                "detailedMessage": "Syntax error near token MATCH",
            },
        )

    transport = httpx.MockTransport(bad_request_handler)
    async with NeptuneClient(transport=transport, max_retries=3) as client:
        with pytest.raises(NeptuneQueryError) as exc_info:
            await client.execute_query("INVALID CYPHER SYNTAX")

        assert exc_info.value.code == "NEPTUNE_QUERY_ERROR"
        assert "Syntax error" in str(exc_info.value)
        assert call_count == 1  # No retries on 400


@pytest.mark.asyncio
async def test_execute_query_timeout_raises_neptune_timeout_error():
    """Verify request timeout raises NeptuneTimeoutError with GRAPH_504_TIMEOUT."""

    def timeout_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Neptune read timeout after 5.0s")

    transport = httpx.MockTransport(timeout_handler)
    async with NeptuneClient(transport=transport, max_retries=1, initial_backoff=0.01) as client:
        with pytest.raises(NeptuneTimeoutError) as exc_info:
            await client.execute_query("MATCH (n) RETURN n")

        assert exc_info.value.code == "GRAPH_504_TIMEOUT"
        assert exc_info.value.status_code == 504
        assert client.consecutive_failures == 1


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_threshold():
    """Verify circuit breaker trips after 5 consecutive failures and blocks queries."""
    call_count = 0

    def timeout_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Query timed out")

    transport = httpx.MockTransport(timeout_handler)
    async with NeptuneClient(
        transport=transport,
        max_retries=0,
        circuit_breaker_threshold=5,
    ) as client:
        for _ in range(5):
            with pytest.raises(NeptuneTimeoutError):
                await client.execute_query("MATCH (n) RETURN n")

        assert client.consecutive_failures == 5
        assert client.is_circuit_open

        # Subsequent query must immediately raise NeptuneCircuitBreakerOpenError
        with pytest.raises(NeptuneCircuitBreakerOpenError) as exc_info:
            await client.execute_query("MATCH (n) RETURN n")

        assert exc_info.value.code == "GRAPH_CIRCUIT_BREAKER_OPEN"
        assert call_count == 5  # No 6th call made to transport

        # Resetting circuit breaker allows calls again
        client.reset_circuit_breaker()
        assert not client.is_circuit_open
        assert client.consecutive_failures == 0


@pytest.mark.asyncio
async def test_health_check_success():
    """Verify health_check() returns True when ping query succeeds."""
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(status_code=200, json={"results": [{"ping": 1}]})
    )
    async with NeptuneClient(transport=transport) as client:
        is_healthy = await client.health_check()
        assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_failure():
    """Verify health_check() returns False when server fails or times out."""
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(status_code=500, text="Internal Error")
    )
    async with NeptuneClient(transport=transport, max_retries=0) as client:
        is_healthy = await client.health_check()
        assert is_healthy is False


@pytest.mark.asyncio
async def test_execute_query_non_retryable_client_error():
    """Verify non-retryable 403 Forbidden raises NeptuneClientError immediately."""
    call_count = 0

    def forbidden_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=403, text="Access Denied")

    transport = httpx.MockTransport(forbidden_handler)
    async with NeptuneClient(transport=transport, max_retries=3) as client:
        with pytest.raises(NeptuneClientError) as exc_info:
            await client.execute_query("MATCH (n) RETURN n")

        assert exc_info.value.status_code == 403
        assert "Access Denied" in str(exc_info.value)
        assert call_count == 1
        assert client.consecutive_failures == 1


@pytest.mark.asyncio
async def test_execute_query_network_error_retry_and_exhaustion():
    """Verify httpx.NetworkError triggers retries and eventually raises NeptuneConnectionError."""
    call_count = 0

    def network_error_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(network_error_handler)
    async with NeptuneClient(transport=transport, max_retries=2, initial_backoff=0.01) as client:
        with pytest.raises(NeptuneConnectionError) as exc_info:
            await client.execute_query("MATCH (n) RETURN n")

        assert call_count == 3  # initial + 2 retries
        assert "Connection refused" in str(exc_info.value)
        assert client.consecutive_failures == 1


@pytest.mark.asyncio
async def test_extract_error_message_non_json_response():
    """Verify error extraction when response is plain text."""
    client = NeptuneClient()
    response = httpx.Response(status_code=500, content=b"Raw text error message")
    error_msg = client._extract_error_message(response)
    assert error_msg == "Raw text error message"
    await client.close()
