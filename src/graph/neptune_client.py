"""Amazon Neptune OpenCypher client for ApexMotion platform.

Supports:
- Connection pooling with httpx.AsyncClient.
- OpenCypher query execution via POST /openCypher with parameter binding.
- Exponential backoff retry logic on transient errors (LLD Section 6.1).
- Circuit breaker pattern tracking consecutive timeouts/failures (LLD Section 6.1).
- Distributed trace ID propagation in request headers (CLAUDE.md Section 10).
- Offline isolation support via injectable HTTP transport.
"""

import asyncio
from typing import Any

import httpx

from src.api.exceptions import AppException
from src.core.config import get_settings
from src.core.logging import get_logger, get_trace_id

logger = get_logger("apexmotion.graph.neptune")

# Transient HTTP status codes eligible for retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ------------------------------------------------------------------------------
# Neptune Custom Exception Hierarchy
# ------------------------------------------------------------------------------


class NeptuneClientError(AppException):
    """Base exception for all Amazon Neptune client errors."""

    def __init__(
        self,
        message: str,
        code: str = "NEPTUNE_CLIENT_ERROR",
        status_code: int = 500,
        details: Any = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class NeptuneConnectionError(NeptuneClientError):
    """Raised when connection to Neptune fails or transient retries are exhausted."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="NEPTUNE_CONNECTION_ERROR",
            message=message,
            status_code=503,
            details=details,
        )


class NeptuneTimeoutError(NeptuneClientError):
    """Raised when Neptune query execution exceeds deadline (LLD Section 6.1)."""

    def __init__(
        self,
        message: str = "Neptune graph query exceeded 5.0 seconds.",
        details: Any = None,
    ):
        super().__init__(
            code="GRAPH_504_TIMEOUT",
            message=message,
            status_code=504,
            details=details,
        )


class NeptuneQueryError(NeptuneClientError):
    """Raised when OpenCypher query syntax or parameters are invalid."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="NEPTUNE_QUERY_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class NeptuneCircuitBreakerOpenError(NeptuneClientError):
    """Raised when consecutive failures exceed threshold and circuit breaker trips."""

    def __init__(
        self,
        message: str = (
            "Neptune circuit breaker is OPEN due to consecutive failures. "
            "Fall back to cached graph topology."
        ),
        details: Any = None,
    ):
        super().__init__(
            code="GRAPH_CIRCUIT_BREAKER_OPEN",
            message=message,
            status_code=503,
            details=details,
        )


# ------------------------------------------------------------------------------
# Neptune OpenCypher Client Implementation
# ------------------------------------------------------------------------------


class NeptuneClient:
    """Asynchronous client for Amazon Neptune OpenCypher graph database."""

    def __init__(
        self,
        endpoint: str | None = None,
        port: int | None = None,
        use_ssl: bool = False,
        timeout: float = 5.0,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        circuit_breaker_threshold: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize Neptune OpenCypher client.

        Args:
            endpoint: Neptune host or IP (defaults to settings.NEPTUNE_ENDPOINT).
            port: Neptune port (defaults to settings.NEPTUNE_PORT, standard 8182).
            use_ssl: Whether to use HTTPS (default False for local dev/mock).
            timeout: Query timeout in seconds (default 5.0s per LLD Section 6.1).
            max_retries: Max retry attempts on transient failures (default 3).
            initial_backoff: Initial exponential backoff in seconds (default 0.5s).
            circuit_breaker_threshold: Consecutive failures before tripping (default 5).
            transport: Optional custom HTTP transport for unit testing / mocking.
        """
        settings = get_settings()
        self.endpoint = endpoint or settings.NEPTUNE_ENDPOINT
        self.port = port or settings.NEPTUNE_PORT
        self.use_ssl = use_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.circuit_breaker_threshold = circuit_breaker_threshold

        scheme = "https" if self.use_ssl else "http"
        self.base_url = f"{scheme}://{self.endpoint}:{self.port}"

        # Circuit breaker state
        self.consecutive_failures = 0
        self.is_circuit_open = False

        # HTTP connection pool configuration
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            limits=limits,
            timeout=httpx.Timeout(self.timeout, connect=2.0),
            transport=transport,
        )

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an OpenCypher query against Amazon Neptune with retries and circuit breaker.

        Args:
            query: OpenCypher query string.
            parameters: Optional query parameter bindings (prevents Cypher injection).

        Returns:
            List of record dictionaries extracted from Neptune JSON response.

        Raises:
            NeptuneCircuitBreakerOpenError: When circuit breaker is currently open.
            NeptuneTimeoutError: When request exceeds configured timeout.
            NeptuneQueryError: When Neptune rejects query (e.g. syntax error).
            NeptuneConnectionError: When retries exhausted or network unavailable.
        """
        if self.is_circuit_open:
            logger.error(
                "Neptune query rejected: Circuit breaker is OPEN (consecutive failures: %d)",
                self.consecutive_failures,
            )
            raise NeptuneCircuitBreakerOpenError()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        trace_id = get_trace_id()
        if trace_id:
            headers["x-trace-id"] = trace_id
            headers["x-request-id"] = trace_id

        payload: dict[str, Any] = {
            "query": query,
            "parameters": parameters or {},
        }

        attempt = 0
        backoff = self.initial_backoff
        last_error_message = ""

        while attempt <= self.max_retries:
            try:
                response = await self._client.post(
                    "/openCypher",
                    json=payload,
                    headers=headers,
                )

                # Successful execution (HTTP 200)
                if response.status_code == 200:
                    self._record_success()
                    data = response.json()
                    results: list[dict[str, Any]] = data.get("results", [])
                    return results

                # Client error (HTTP 400 Bad Request) - non-retryable
                if response.status_code == 400:
                    error_detail = self._extract_error_message(response)
                    logger.warning(
                        "Neptune query rejected with 400 Bad Request: %s",
                        error_detail,
                    )
                    raise NeptuneQueryError(
                        message=f"Neptune query rejected: {error_detail}",
                        details={"query": query, "response": error_detail},
                    )

                # Transient server errors eligible for retry
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error_message = f"HTTP {response.status_code}: {response.text}"
                    logger.warning(
                        "Neptune transient failure on attempt %d/%d: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        last_error_message,
                    )
                else:
                    # Non-retryable HTTP error
                    last_error_message = f"HTTP {response.status_code}: {response.text}"
                    self._record_failure()
                    raise NeptuneClientError(
                        message=f"Neptune request failed: {last_error_message}",
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException as exc:
                last_error_message = f"Request timed out: {exc}"
                logger.warning(
                    "Neptune timeout on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    last_error_message,
                )
            except httpx.NetworkError as exc:
                last_error_message = f"Network connection error: {exc}"
                logger.warning(
                    "Neptune network error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    last_error_message,
                )

            # Evaluate retry loop
            attempt += 1
            if attempt <= self.max_retries:
                logger.info(
                    "Retrying Neptune query in %.2fs (attempt %d of %d)",
                    backoff,
                    attempt + 1,
                    self.max_retries + 1,
                )
                await asyncio.sleep(backoff)
                backoff *= 2.0

        # Max retries exhausted
        self._record_failure()
        if "timed out" in last_error_message.lower():
            raise NeptuneTimeoutError(
                message=f"Neptune query timed out after {self.max_retries} retries: {last_error_message}"
            )
        raise NeptuneConnectionError(
            message=f"Max retries ({self.max_retries}) exceeded: {last_error_message}"
        )

    async def health_check(self) -> bool:
        """Probe Neptune cluster health by executing a ping query.

        Returns:
            True if Neptune responds successfully, False otherwise.
        """
        try:
            results = await self.execute_query("RETURN 1 AS ping")
            return len(results) > 0 and results[0].get("ping") == 1
        except Exception as exc:
            logger.warning("Neptune health check probe failed: %s", exc)
            return False

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker state after topology recovery."""
        self.consecutive_failures = 0
        self.is_circuit_open = False
        logger.info("Neptune circuit breaker manually reset to CLOSED")

    def _record_success(self) -> None:
        """Reset consecutive failure counter upon successful execution."""
        self.consecutive_failures = 0
        self.is_circuit_open = False

    def _record_failure(self) -> None:
        """Increment consecutive failures and trip circuit breaker if threshold reached."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.is_circuit_open = True
            logger.critical(
                "Neptune circuit breaker TRIPPED to OPEN after %d consecutive failures. "
                "All future queries will fail-fast until reset.",
                self.consecutive_failures,
            )

    def _extract_error_message(self, response: httpx.Response) -> str:
        """Extract detailed error message from Neptune JSON or text response."""
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("detailedMessage") or data.get("message") or str(data)
            return str(data)
        except Exception:
            return response.text or f"HTTP {response.status_code}"

    async def close(self) -> None:
        """Close underlying HTTP client connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "NeptuneClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()
