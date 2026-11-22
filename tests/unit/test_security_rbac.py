"""Unit tests for Okta JWT validation and require_role() RBAC guard.

Validates:
- Role enumeration and hierarchy (supply_chain_analyst, category_manager, procurement_director, vp_supply_chain, system_admin)
- AuthenticatedUser model and role checking utilities
- JWT token generation and validation (signature, claims, expiration, malformed)
- FastAPI dependencies: get_current_user and require_role() guards
- Role extraction across multiple standard OIDC/Okta claim locations (roles, groups, realm_access, scp)
- Error handling adhering to standard ApexMotion error envelopes (401 AUTHENTICATION_REQUIRED, 403 INSUFFICIENT_ROLE)
"""

from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from src.api.exceptions import AuthenticationException, AuthorizationException
from src.core.security import (
    ROLE_HIERARCHY,
    AuthenticatedUser,
    UserRole,
    create_access_token,
    get_current_user,
    require_any_role,
    require_role,
    validate_jwt_token,
)


def test_user_role_enum_and_hierarchy():
    """Verify that all standard roles exist and their hierarchy levels reflect CLAUDE.md."""
    assert UserRole.ANALYST == "analyst"
    assert UserRole.SUPPLY_CHAIN_ANALYST == "supply_chain_analyst"
    assert UserRole.CATEGORY_MANAGER == "category_manager"
    assert UserRole.PROCUREMENT_DIRECTOR == "procurement_director"
    assert UserRole.VP_SUPPLY_CHAIN == "vp_supply_chain"
    assert UserRole.SYSTEM_ADMIN == "system_admin"

    # Hierarchy validation
    assert ROLE_HIERARCHY[UserRole.ANALYST.value] == 10
    assert ROLE_HIERARCHY[UserRole.SUPPLY_CHAIN_ANALYST.value] == 10
    assert ROLE_HIERARCHY[UserRole.CATEGORY_MANAGER.value] == 20
    assert ROLE_HIERARCHY[UserRole.PROCUREMENT_DIRECTOR.value] == 30
    assert ROLE_HIERARCHY[UserRole.VP_SUPPLY_CHAIN.value] == 40
    assert ROLE_HIERARCHY[UserRole.SYSTEM_ADMIN.value] == 50


def test_authenticated_user_model_role_checks():
    """Verify AuthenticatedUser role-checking helper methods."""
    user = AuthenticatedUser(
        user_id="usr-123",
        email="analyst@apexmotion.com",
        roles=["supply_chain_analyst"],
    )

    # Exact match and alias
    assert user.has_role(UserRole.SUPPLY_CHAIN_ANALYST) is True
    assert user.has_role(UserRole.ANALYST) is True
    assert user.has_role("analyst") is True
    assert user.has_role(UserRole.CATEGORY_MANAGER) is False

    # Higher role checks
    manager = AuthenticatedUser(
        user_id="usr-456",
        email="mgr@apexmotion.com",
        roles=["category_manager"],
    )
    assert manager.has_role(UserRole.CATEGORY_MANAGER) is True
    assert manager.has_role(UserRole.ANALYST, allow_higher=True) is True
    assert manager.has_role(UserRole.ANALYST, allow_higher=False) is False
    assert manager.is_at_least(UserRole.ANALYST) is True
    assert manager.is_at_least(UserRole.PROCUREMENT_DIRECTOR) is False


def test_token_generation_and_decoding_valid():
    """Verify that a freshly generated JWT token decodes to the expected AuthenticatedUser."""
    token = create_access_token(
        subject="usr-test-01",
        email="director@apexmotion.com",
        roles=["procurement_director"],
        name="Marcus Brody",
    )

    user = validate_jwt_token(token)
    assert user.user_id == "usr-test-01"
    assert user.email == "director@apexmotion.com"
    assert user.name == "Marcus Brody"
    assert "procurement_director" in user.roles
    assert user.is_at_least(UserRole.CATEGORY_MANAGER) is True


def test_token_decoding_expired_raises_401():
    """Verify that an expired JWT token raises AuthenticationException."""
    token = create_access_token(
        subject="usr-expired",
        roles=["analyst"],
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )

    with pytest.raises(AuthenticationException) as exc_info:
        validate_jwt_token(token)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.message.lower()


def test_token_decoding_invalid_signature_raises_401():
    """Verify that a token signed with an invalid secret raises AuthenticationException."""
    token = create_access_token(
        subject="usr-tampered",
        roles=["analyst"],
        key="wrong_secret_key_that_does_not_match_settings",
    )

    with pytest.raises(AuthenticationException) as exc_info:
        validate_jwt_token(token)

    assert exc_info.value.status_code == 401


def test_token_decoding_missing_or_malformed_raises_401():
    """Verify that malformed token strings raise AuthenticationException."""
    for malformed in ["", "not-a-valid-jwt", "part1.part2", "invalid.jwt.token"]:
        with pytest.raises(AuthenticationException) as exc_info:
            validate_jwt_token(malformed)
        assert exc_info.value.status_code == 401


def test_claims_role_extraction_sources():
    """Verify that roles are extracted from groups, realm_access, and scp claims."""
    # Test 'groups' claim (standard Okta)
    t_groups = create_access_token(
        subject="usr-groups",
        additional_claims={"groups": ["category_manager", "Everyone"]},
    )
    u_groups = validate_jwt_token(t_groups)
    assert "category_manager" in u_groups.roles

    # Test 'realm_access' claim (Keycloak)
    t_keycloak = create_access_token(
        subject="usr-kc",
        additional_claims={"realm_access": {"roles": ["vp_supply_chain"]}},
    )
    u_kc = validate_jwt_token(t_keycloak)
    assert "vp_supply_chain" in u_kc.roles

    # Test 'scp' scope claim
    t_scp = create_access_token(
        subject="usr-scp",
        additional_claims={"scp": ["openid", "profile", "role:system_admin"]},
    )
    u_scp = validate_jwt_token(t_scp)
    assert "system_admin" in u_scp.roles


@pytest.mark.asyncio
async def test_get_current_user_dependency_success():
    """Verify get_current_user parses valid Bearer token from Authorization header."""
    token = create_access_token(subject="usr-bearer", roles=["analyst"])
    auth_header = f"Bearer {token}"

    user = await get_current_user(authorization=auth_header)
    assert user.user_id == "usr-bearer"
    assert "analyst" in user.roles


@pytest.mark.asyncio
async def test_get_current_user_missing_or_invalid_header_raises_401():
    """Verify get_current_user rejects missing or non-Bearer authorization headers."""
    # Missing header
    with pytest.raises(AuthenticationException) as exc1:
        await get_current_user(authorization=None)
    assert exc1.value.status_code == 401

    # Basic auth instead of Bearer
    with pytest.raises(AuthenticationException) as exc2:
        await get_current_user(authorization="Basic dXNlcjpwYXNz")
    assert exc2.value.status_code == 401

    # Malformed Bearer
    with pytest.raises(AuthenticationException) as exc3:
        await get_current_user(authorization="Bearer")
    assert exc3.value.status_code == 401


@pytest.mark.asyncio
async def test_require_role_guard_logic():
    """Verify require_role dependency callable authorizes allowed roles and rejects unauthorized ones."""
    analyst_user = AuthenticatedUser(user_id="1", roles=["analyst"])
    mgr_user = AuthenticatedUser(user_id="2", roles=["category_manager"])
    director_user = AuthenticatedUser(user_id="3", roles=["procurement_director"])

    # Guard requiring category_manager (with allow_higher=True default)
    mgr_guard = require_role(UserRole.CATEGORY_MANAGER)

    # Analyst fails
    with pytest.raises(AuthorizationException) as exc1:
        await mgr_guard(current_user=analyst_user)
    assert exc1.value.status_code == 403

    # Category manager passes
    res_mgr = await mgr_guard(current_user=mgr_user)
    assert res_mgr.user_id == "2"

    # Director passes (hierarchy elevation)
    res_dir = await mgr_guard(current_user=director_user)
    assert res_dir.user_id == "3"

    # Guard with allow_higher=False (strict exact role)
    strict_guard = require_role(UserRole.CATEGORY_MANAGER, allow_higher=False)
    with pytest.raises(AuthorizationException) as exc2:
        await strict_guard(current_user=director_user)
    assert exc2.value.status_code == 403


@pytest.mark.asyncio
async def test_require_any_role_guard_logic():
    """Verify require_any_role permits matching any of specified roles."""
    user = AuthenticatedUser(user_id="u1", roles=["category_manager"])

    guard = require_any_role(UserRole.SYSTEM_ADMIN, UserRole.CATEGORY_MANAGER)
    res = await guard(current_user=user)
    assert res.user_id == "u1"

    failing_guard = require_any_role(
        UserRole.VP_SUPPLY_CHAIN, UserRole.SYSTEM_ADMIN, allow_higher=False
    )
    with pytest.raises(AuthorizationException) as exc:
        await failing_guard(current_user=user)
    assert exc.value.status_code == 403


def test_fastapi_route_integration_with_security():
    """Verify complete FastAPI route request flow with authentication and RBAC guards."""
    from src.api.main import app

    analyst_guard = require_role(UserRole.ANALYST)
    manager_guard = require_role(UserRole.CATEGORY_MANAGER)

    @app.get("/api/v1/test-analyst-only")
    async def analyst_route(user: Annotated[AuthenticatedUser, Depends(analyst_guard)]):
        return {"status": "ok", "user": user.user_id}

    @app.post("/api/v1/test-manager-only")
    async def manager_route(
        user: Annotated[AuthenticatedUser, Depends(manager_guard)],
    ):
        return {"status": "authorized", "user": user.user_id}

    client = TestClient(app, raise_server_exceptions=False)

    # 1. No Authorization header -> 401
    resp_no_auth = client.get("/api/v1/test-analyst-only")
    assert resp_no_auth.status_code == 401
    assert resp_no_auth.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # 2. Analyst token accesses analyst-only route -> 200
    analyst_token = create_access_token(subject="user-a", roles=["analyst"])
    resp_analyst_ok = client.get(
        "/api/v1/test-analyst-only",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert resp_analyst_ok.status_code == 200
    assert resp_analyst_ok.json()["user"] == "user-a"

    # 3. Analyst token accesses manager-only route -> 403
    resp_analyst_forbidden = client.post(
        "/api/v1/test-manager-only",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert resp_analyst_forbidden.status_code == 403
    assert resp_analyst_forbidden.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 4. Manager token accesses manager-only route -> 200
    mgr_token = create_access_token(subject="user-m", roles=["category_manager"])
    resp_mgr_ok = client.post(
        "/api/v1/test-manager-only",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert resp_mgr_ok.status_code == 200
    assert resp_mgr_ok.json()["user"] == "user-m"
