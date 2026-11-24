"""Unit tests for centralized error standardization and no-op mutation guard (P11-6).

Verifies:
- Standardized Error Envelopes (CLAUDE.md Section 10):
    * All errors return exact format: `{"error": {"code": str, "message": str, "trace_id": str}}`
    * No raw stack traces or internal secrets leaked to the client
    * `X-Request-ID` and `X-Trace-ID` propagated to error response envelope
- Standard Error Codes:
    * 400 `VALIDATION_ERROR` (Pydantic / schema validation failures)
    * 401 `AUTHENTICATION_REQUIRED` (missing or invalid credentials)
    * 403 `INSUFFICIENT_ROLE` (RBAC authorization failures)
    * 404 `NOT_FOUND` (entity does not exist)
    * 405 `METHOD_NOT_ALLOWED` (HTTP method not supported)
    * 409 `CONFLICT` / `NO_OP_MUTATION_REJECTED` (state transition conflicts and no-op guards)
    * 409 `TOKEN_REPLAY` (replayed cryptographic tokens)
    * 429 `RATE_LIMITED` (rate limiting)
    * 500 `INTERNAL_ERROR` (unhandled exceptions masked)
    * 503 `DEPENDENCY_UNAVAILABLE` (external infrastructure down)
- No-Op Mutation Guards (CLAUDE.md Section 20):
    * `check_no_op_mutation` raises `NoOpMutationException` when `before_state == after_state`
    * Re-acknowledging an already acknowledged alert returns 409 `NO_OP_MUTATION_REJECTED`
    * Re-signing an already approved HITL record returns 409 `CONFLICT` / `NO_OP_MUTATION_REJECTED`
- Database Integrity & Exception Mapping:
    * SQLAlchemy `IntegrityError` mapped to clean 409 error envelope without SQL leaks
    * Domain token exceptions (expired, invalid signature, replay) correctly formatted
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from src.api.exceptions import (
    NoOpMutationException,
    format_error_response,
)
from src.api.main import app
from src.api.routes.error_handlers import (
    check_no_op_mutation,
)
from src.core.hitl_tokens import (
    HITLTokenService,
    TokenExpiredError,
    TokenSignatureInvalidError,
)
from src.core.security import UserRole, create_access_token
from src.database.repositories.hitl_approval_repository import (
    TokenReplayError,
)
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from starlette.exceptions import HTTPException as StarletteHTTPException

# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------


def _auth_header(role: UserRole = UserRole.ANALYST) -> dict[str, str]:
    """Generate authorization headers for a specific role."""
    token = create_access_token(
        subject=f"usr-{role.value}",
        roles=[role],
        email=f"{role.value}@apexmotion.com",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_token_service() -> HITLTokenService:
    """Fixture providing an isolated KMS ECDSA token service."""
    return HITLTokenService()


# ------------------------------------------------------------------------------
# 1. Error Formatting & Structure Tests
# ------------------------------------------------------------------------------


def test_format_error_response_standard_structure():
    """Verify format_error_response generates exact {error: {code, message, trace_id}} shape."""
    trace = str(uuid.uuid4())
    result = format_error_response(
        code="TEST_ERROR",
        message="A test error message",
        trace_id=trace,
    )

    assert "error" in result
    assert result["error"]["code"] == "TEST_ERROR"
    assert result["error"]["message"] == "A test error message"
    assert result["error"]["trace_id"] == trace
    assert "details" not in result["error"]


def test_format_error_response_with_details():
    """Verify format_error_response includes optional details dictionary."""
    trace = str(uuid.uuid4())
    details = {"field": "username", "issue": "required"}
    result = format_error_response(
        code="VALIDATION_ERROR",
        message="Field validation failed",
        trace_id=trace,
        details=details,
    )

    assert result["error"]["details"] == details


# ------------------------------------------------------------------------------
# 2. No-Op Guard Helper Tests (CLAUDE.md Section 20)
# ------------------------------------------------------------------------------


def test_check_no_op_mutation_rejects_identical_states():
    """Verify check_no_op_mutation raises NoOpMutationException when before_state == after_state."""
    entity_id = "ALT-12345"

    with pytest.raises(NoOpMutationException) as exc_info:
        check_no_op_mutation(
            entity_id=entity_id,
            current_state="ACKNOWLEDGED",
            target_state="ACKNOWLEDGED",
        )

    exc = exc_info.value
    assert exc.code == "NO_OP_MUTATION_REJECTED"
    assert exc.status_code == 409
    assert entity_id in exc.message
    assert "no-op" in exc.message.lower()


def test_check_no_op_mutation_allows_distinct_states():
    """Verify check_no_op_mutation succeeds without error when target_state != current_state."""
    # Should not raise
    check_no_op_mutation(
        entity_id="ALT-12345",
        current_state="OPEN",
        target_state="ACKNOWLEDGED",
    )


def test_no_op_mutation_exception_defaults():
    """Verify NoOpMutationException defaults code to NO_OP_MUTATION_REJECTED and status to 409."""
    exc = NoOpMutationException("No changes applied.")
    assert exc.code == "NO_OP_MUTATION_REJECTED"
    assert exc.status_code == 409
    assert exc.message == "No changes applied."


# ------------------------------------------------------------------------------
# 3. HTTP Client Error Envelope & Status Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_400_envelope():
    """Verify schema validation error returns 400 VALIDATION_ERROR envelope with trace_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send invalid JSON body to /api/v1/risk/evaluate
        resp = await client.post(
            "/api/v1/risk/evaluate",
            json={"supplier_id": 12345, "component_sku": None},  # Missing required fields
            headers=_auth_header(UserRole.ANALYST),
        )

        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "message" in body["error"]
        assert "trace_id" in body["error"]
        assert body["error"]["trace_id"] is not None


@pytest.mark.asyncio
async def test_authentication_error_401_envelope():
    """Verify unauthenticated request returns 401 AUTHENTICATION_REQUIRED with trace_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/alerts")

        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert "message" in body["error"]
        assert "trace_id" in body["error"]


@pytest.mark.asyncio
async def test_authorization_error_403_envelope():
    """Verify unauthorized role request returns 403 INSUFFICIENT_ROLE with trace_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Analyst attempting to acknowledge an alert (requires Category Manager+)
        alert_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge",
            headers=_auth_header(UserRole.ANALYST),
        )

        assert resp.status_code == 403
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "INSUFFICIENT_ROLE"
        assert "message" in body["error"]
        assert "trace_id" in body["error"]


@pytest.mark.asyncio
async def test_not_found_error_404_envelope():
    """Verify not found request returns 404 NOT_FOUND with trace_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request a route that does not exist
        resp = await client.get(
            "/api/v1/nonexistent-endpoint-path",
            headers=_auth_header(UserRole.ANALYST),
        )

        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "NOT_FOUND"
        assert "message" in body["error"]
        assert "trace_id" in body["error"]


@pytest.mark.asyncio
async def test_not_found_entity_404_envelope():
    """Verify requesting a non-existent entity returns 404 NOT_FOUND with trace_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        random_id = str(uuid.uuid4())

        with patch("src.api.routes.risk_routes.RiskAlertRepository", return_value=mock_repo):
            resp = await client.get(
                f"/api/v1/alerts/{random_id}",
                headers=_auth_header(UserRole.ANALYST),
            )

            assert resp.status_code == 404
            body = resp.json()
            assert "error" in body
            assert body["error"]["code"] == "NOT_FOUND"
            assert "trace_id" in body["error"]


@pytest.mark.asyncio
async def test_method_not_allowed_405_envelope():
    """Verify 405 Method Not Allowed returns standardized error envelope."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST to /health which is a GET-only endpoint
        resp = await client.post("/health")

        assert resp.status_code == 405
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert "trace_id" in body["error"]


@pytest.mark.asyncio
async def test_trace_id_propagation_in_error_envelope():
    """Verify custom X-Request-ID or X-Trace-ID header is echoed in error.trace_id."""
    custom_trace = f"trace-custom-{uuid.uuid4().hex[:12]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/alerts",
            headers={"X-Trace-ID": custom_trace},
        )

        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["trace_id"] == custom_trace
        assert resp.headers.get("X-Trace-ID") == custom_trace


# ------------------------------------------------------------------------------
# 4. Unhandled Exception & Information Disclosure Defense (500)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unhandled_exception_masks_internal_details_and_tracebacks():
    """Verify unexpected internal exception returns generic 500 INTERNAL_ERROR masking stack trace."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Patch a service or route to raise an unexpected internal exception with sensitive text
        with patch.object(
            RiskAlertRepository,
            "get_by_id",
            side_effect=RuntimeError("FATAL: secret_db_password_123 leaked in postgres query!"),
        ):
            random_id = str(uuid.uuid4())
            resp = await client.get(
                f"/api/v1/alerts/{random_id}",
                headers=_auth_header(UserRole.ANALYST),
            )

            assert resp.status_code == 500
            body = resp.json()
            assert "error" in body
            assert body["error"]["code"] == "INTERNAL_ERROR"
            # Crucial: the sensitive internal string MUST NOT be in the client response
            assert "secret_db_password" not in body["error"]["message"]
            assert "traceback" not in body["error"]["message"].lower()
            assert "trace_id" in body["error"]


# ------------------------------------------------------------------------------
# 5. Database Integrity & Domain Exception Handler Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integrity_error_mapped_to_conflict():
    """Verify SQLAlchemy IntegrityError is caught and formatted as 409 CONFLICT."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            RiskAlertRepository,
            "get_by_id",
            side_effect=IntegrityError(
                statement="INSERT INTO risk_alerts ...",
                params={},
                orig=Exception("duplicate key value violates unique constraint"),
            ),
        ):
            random_id = str(uuid.uuid4())
            resp = await client.get(
                f"/api/v1/alerts/{random_id}",
                headers=_auth_header(UserRole.ANALYST),
            )

            assert resp.status_code == 409
            body = resp.json()
            assert body["error"]["code"] == "CONFLICT"
            # Ensure raw SQL statement is NOT leaked
            assert "INSERT INTO" not in body["error"]["message"]


# ------------------------------------------------------------------------------
# 6. No-Op Guard in Alert & Approval State Transitions
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_acknowledge_no_op_mutation_rejected():
    """Verify acknowledging an already acknowledged alert returns 409 NO_OP_MUTATION_REJECTED."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mock alert already in ACKNOWLEDGED status
        mock_alert = MagicMock()
        mock_alert.id = uuid.uuid4()
        mock_alert.status = "ACKNOWLEDGED"

        with patch.object(RiskAlertRepository, "get_by_id", return_value=mock_alert):
            resp = await client.post(
                f"/api/v1/alerts/{mock_alert.id}/acknowledge",
                headers=_auth_header(UserRole.CATEGORY_MANAGER),
            )

            assert resp.status_code == 409
            body = resp.json()
            assert body["error"]["code"] in ("NO_OP_MUTATION_REJECTED", "CONFLICT")
            assert "already" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_approval_sign_no_op_on_terminal_approved_record():
    """Verify attempting to sign an already APPROVED record is rejected with 409 CONFLICT."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mock_approval = MagicMock()
        mock_approval.id = uuid.uuid4()
        mock_approval.status = "APPROVED"

        with patch(
            "src.api.routes.approval_routes.HITLApprovalRepository.get_by_id",
            return_value=mock_approval,
        ):
            resp = await client.post(
                f"/api/v1/approvals/{mock_approval.id}/sign",
                json={"token": "some.token.value"},
                headers=_auth_header(UserRole.CATEGORY_MANAGER),
            )

            assert resp.status_code == 409
            body = resp.json()
            assert body["error"]["code"] in ("CONFLICT", "NO_OP_MUTATION_REJECTED")
            assert "APPROVED" in body["error"]["message"]


# ------------------------------------------------------------------------------
# 7. Direct Handler Unit Invocations for Domain Exceptions
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_replay_handler_direct_invocation():
    """Verify token_replay_exception_handler returns 409 TOKEN_REPLAY envelope."""
    from src.api.routes.error_handlers import token_replay_exception_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-replay-test-123"
    exc = TokenReplayError("Hash abc123 already exists in database index.")

    response = await token_replay_exception_handler(mock_req, exc)
    assert response.status_code == 409
    body = response.body.decode()
    assert "TOKEN_REPLAY" in body
    assert "trace-replay-test-123" in body


@pytest.mark.asyncio
async def test_token_expired_handler_direct_invocation():
    """Verify token_expired_exception_handler returns 400 TOKEN_EXPIRED envelope."""
    from src.api.routes.error_handlers import token_expired_exception_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-expired-test-456"
    exc = TokenExpiredError("Token expired 5 minutes ago.")

    response = await token_expired_exception_handler(mock_req, exc)
    assert response.status_code == 400
    body = response.body.decode()
    assert "TOKEN_EXPIRED" in body
    assert "trace-expired-test-456" in body


@pytest.mark.asyncio
async def test_token_signature_invalid_handler_direct_invocation():
    """Verify token_signature_invalid_exception_handler returns 400 INVALID_TOKEN_SIGNATURE envelope."""
    from src.api.routes.error_handlers import token_signature_invalid_exception_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-sig-test-789"
    exc = TokenSignatureInvalidError("ECDSA signature failed verification.")

    response = await token_signature_invalid_exception_handler(mock_req, exc)
    assert response.status_code == 400
    body = response.body.decode()
    assert "INVALID_TOKEN_SIGNATURE" in body
    assert "trace-sig-test-789" in body


@pytest.mark.asyncio
async def test_integrity_error_token_hash_mapped_to_token_replay():
    """Verify integrity_error_handler detects token_hash in error string and returns TOKEN_REPLAY."""
    from src.api.routes.error_handlers import integrity_error_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-int-token-hash"
    exc = IntegrityError(
        statement="INSERT INTO hitl_approvals ...",
        params={},
        orig=Exception(
            "duplicate key value violates unique constraint 'uq_hitl_approvals_token_hash'"
        ),
    )

    response = await integrity_error_handler(mock_req, exc)
    assert response.status_code == 409
    body = response.body.decode()
    assert "TOKEN_REPLAY" in body
    assert "trace-int-token-hash" in body
    assert "INSERT INTO" not in body


@pytest.mark.asyncio
async def test_starlette_http_exception_429_rate_limited():
    """Verify starlette_http_exception_handler maps 429 to RATE_LIMITED code."""
    from src.api.routes.error_handlers import starlette_http_exception_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-rate-429"
    exc = StarletteHTTPException(status_code=429, detail="Too many requests. Please slow down.")

    response = await starlette_http_exception_handler(mock_req, exc)
    assert response.status_code == 429
    body = response.body.decode()
    assert "RATE_LIMITED" in body
    assert "Too many requests" in body


@pytest.mark.asyncio
async def test_starlette_http_exception_503_dependency_unavailable():
    """Verify starlette_http_exception_handler maps 503 to DEPENDENCY_UNAVAILABLE code."""
    from src.api.routes.error_handlers import starlette_http_exception_handler

    mock_req = MagicMock()
    mock_req.state.trace_id = "trace-dep-503"
    exc = StarletteHTTPException(status_code=503, detail="Amazon Neptune connection failed.")

    response = await starlette_http_exception_handler(mock_req, exc)
    assert response.status_code == 503
    body = response.body.decode()
    assert "DEPENDENCY_UNAVAILABLE" in body
    assert "Amazon Neptune connection failed" in body
