"""Unit tests for Demo Okta tokens across all platform personas.

Validates:
- Definition and completeness of all 5 personas (analyst, category_manager, procurement_director, vp_supply_chain, system_admin)
- Demographic metadata, spend authority levels, and group claims alignment with CLAUDE.md Section 3
- Generation and cryptographic decoding of demo tokens via validate_jwt_token()
- RBAC permissions enforcement across routes for each persona token
- CLI demo token generation script execution and output formats (text, JSON, env)
"""

import json
import subprocess
import sys
from decimal import Decimal
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from src.api.exceptions import AppException
from src.core.demo_auth import (
    DEMO_PERSONAS,
    DemoPersona,
    generate_all_demo_tokens,
    generate_demo_token,
    get_demo_persona,
)
from src.core.security import (
    AuthenticatedUser,
    UserRole,
    require_role,
    validate_jwt_token,
)


def test_demo_personas_registry_completeness():
    """Verify that all five mandatory personas exist in the registry with expected attributes."""
    expected_personas = [
        "analyst",
        "category_manager",
        "procurement_director",
        "vp_supply_chain",
        "system_admin",
    ]

    for p_id in expected_personas:
        assert p_id in DEMO_PERSONAS
        persona = DEMO_PERSONAS[p_id]
        assert isinstance(persona, DemoPersona)
        assert persona.persona_id == p_id
        assert len(persona.name) > 0
        assert "@apexmotion.com" in persona.email
        assert len(persona.groups) > 0
        assert persona.user_id.startswith("usr-")


def test_demo_persona_spend_authority_thresholds():
    """Verify spend authority metadata adheres to BR-RULE-001 monetary limits."""
    # Analyst has zero spend authority (read-only)
    assert DEMO_PERSONAS["analyst"].spend_authority_usd is None or DEMO_PERSONAS[
        "analyst"
    ].spend_authority_usd == Decimal("0.00")

    # Category Manager has <= $25,000 spend limit
    cat_mgr = DEMO_PERSONAS["category_manager"]
    assert isinstance(cat_mgr.spend_authority_usd, Decimal)
    assert cat_mgr.spend_authority_usd == Decimal("25000.00")

    # Procurement Director has <= $100,000 spend limit
    director = DEMO_PERSONAS["procurement_director"]
    assert isinstance(director.spend_authority_usd, Decimal)
    assert director.spend_authority_usd == Decimal("100000.00")

    # VP Supply Chain has dual-signoff authority (> $100,000)
    vp = DEMO_PERSONAS["vp_supply_chain"]
    assert vp.spend_authority_usd is not None
    assert vp.spend_authority_usd > Decimal("100000.00")

    # System Admin has system actions only
    assert DEMO_PERSONAS["system_admin"].role == UserRole.SYSTEM_ADMIN


def test_get_demo_persona_lookup_and_aliases():
    """Verify get_demo_persona resolves by key, role, and canonical aliases."""
    # By ID
    assert get_demo_persona("analyst").persona_id == "analyst"
    assert get_demo_persona("category_manager").persona_id == "category_manager"

    # By UserRole
    assert get_demo_persona(UserRole.PROCUREMENT_DIRECTOR).persona_id == "procurement_director"
    assert get_demo_persona(UserRole.VP_SUPPLY_CHAIN).persona_id == "vp_supply_chain"
    assert get_demo_persona(UserRole.SYSTEM_ADMIN).persona_id == "system_admin"

    # By Aliases
    assert get_demo_persona("supply_chain_analyst").persona_id == "analyst"
    assert get_demo_persona("vp").persona_id == "vp_supply_chain"
    assert get_demo_persona("director").persona_id == "procurement_director"
    assert get_demo_persona("admin").persona_id == "system_admin"

    # Invalid persona raises KeyError
    with pytest.raises(KeyError):
        get_demo_persona("non_existent_persona")


def test_generate_demo_token_and_decode_all_personas():
    """Verify generate_demo_token generates valid signed JWTs for each persona."""
    # Test individual generation with string key, UserRole, and DemoPersona instance
    tok1 = generate_demo_token("analyst")
    assert isinstance(tok1, str)
    u1 = validate_jwt_token(tok1)
    assert u1.user_id == "usr-alex-chen"

    tok2 = generate_demo_token(UserRole.CATEGORY_MANAGER)
    assert isinstance(tok2, str)
    u2 = validate_jwt_token(tok2)
    assert u2.user_id == "usr-priya-sharma"

    tok3 = generate_demo_token(DEMO_PERSONAS["vp_supply_chain"])
    assert isinstance(tok3, str)
    u3 = validate_jwt_token(tok3)
    assert u3.user_id == "usr-elena-rostova"

    tokens = generate_all_demo_tokens()
    assert len(tokens) == 5

    for p_id, token_str in tokens.items():
        assert isinstance(token_str, str)
        assert len(token_str.split(".")) == 3  # Valid JWT format: header.payload.signature

        user: AuthenticatedUser = validate_jwt_token(token_str)
        persona = DEMO_PERSONAS[p_id]

        assert user.user_id == persona.user_id
        assert user.email == persona.email
        assert user.name == persona.name
        assert persona.role.value in user.roles or (
            p_id == "analyst" and "supply_chain_analyst" in user.roles
        )


def test_demo_tokens_rbac_route_authorization_pipeline():
    """Verify that each generated demo token behaves correctly against FastAPI RBAC guards."""
    test_app = FastAPI()

    @test_app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    analyst_guard = require_role(UserRole.ANALYST)
    manager_guard = require_role(UserRole.CATEGORY_MANAGER)
    director_guard = require_role(UserRole.PROCUREMENT_DIRECTOR)
    admin_guard = require_role(UserRole.SYSTEM_ADMIN, allow_higher=False)

    @test_app.get("/api/v1/analyst-feed")
    async def analyst_route(user: Annotated[AuthenticatedUser, Depends(analyst_guard)]):
        return {"authorized": True, "user": user.user_id}

    @test_app.post("/api/v1/manager-approval")
    async def manager_route(
        user: Annotated[AuthenticatedUser, Depends(manager_guard)],
    ):
        return {"authorized": True, "user": user.user_id}

    @test_app.post("/api/v1/director-override")
    async def director_route(
        user: Annotated[AuthenticatedUser, Depends(director_guard)],
    ):
        return {"authorized": True, "user": user.user_id}

    @test_app.post("/api/v1/admin-ops")
    async def admin_route(
        user: Annotated[AuthenticatedUser, Depends(admin_guard)],
    ):
        return {"authorized": True, "user": user.user_id}

    client = TestClient(test_app, raise_server_exceptions=False)

    tokens = generate_all_demo_tokens()
    analyst_token = tokens["analyst"]
    manager_token = tokens["category_manager"]
    director_token = tokens["procurement_director"]
    vp_token = tokens["vp_supply_chain"]
    admin_token = tokens["system_admin"]

    # 1. Analyst token tests
    # Can access analyst route
    r1 = client.get("/api/v1/analyst-feed", headers={"Authorization": f"Bearer {analyst_token}"})
    assert r1.status_code == 200
    # Cannot access manager approval route -> 403
    r2 = client.post(
        "/api/v1/manager-approval", headers={"Authorization": f"Bearer {analyst_token}"}
    )
    assert r2.status_code == 403

    # 2. Category Manager token tests
    # Can access analyst route
    r3 = client.get("/api/v1/analyst-feed", headers={"Authorization": f"Bearer {manager_token}"})
    assert r3.status_code == 200
    # Can access manager approval route
    r4 = client.post(
        "/api/v1/manager-approval", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert r4.status_code == 200
    # Cannot access director override route -> 403
    r5 = client.post(
        "/api/v1/director-override", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert r5.status_code == 403

    # 3. Procurement Director token tests
    # Can access manager approval route
    r6 = client.post(
        "/api/v1/manager-approval", headers={"Authorization": f"Bearer {director_token}"}
    )
    assert r6.status_code == 200
    # Can access director override route
    r7 = client.post(
        "/api/v1/director-override", headers={"Authorization": f"Bearer {director_token}"}
    )
    assert r7.status_code == 200

    # 4. VP Supply Chain token tests
    # Hierarchical elevation allows VP to access director route
    r8 = client.post("/api/v1/director-override", headers={"Authorization": f"Bearer {vp_token}"})
    assert r8.status_code == 200

    # 5. System Admin token tests
    # Can access strict admin route
    r9 = client.post("/api/v1/admin-ops", headers={"Authorization": f"Bearer {admin_token}"})
    assert r9.status_code == 200
    # Analyst cannot access admin route
    r10 = client.post("/api/v1/admin-ops", headers={"Authorization": f"Bearer {analyst_token}"})
    assert r10.status_code == 403


def test_cli_script_generate_demo_tokens_execution():
    """Verify that scripts/generate_demo_tokens.py runs and outputs formatted JSON/text."""
    # Test JSON output
    res_json = subprocess.run(
        [sys.executable, "scripts/generate_demo_tokens.py", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(res_json.stdout)
    assert "tokens" in data
    assert "personas" in data
    assert len(data["tokens"]) == 5
    assert "analyst" in data["tokens"]
    assert "vp_supply_chain" in data["tokens"]

    # Test text output
    res_text = subprocess.run(
        [sys.executable, "scripts/generate_demo_tokens.py", "--format", "text"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ApexMotion Demo Persona Tokens" in res_text.stdout
    assert "Alex Chen" in res_text.stdout
    assert "Authorization: Bearer" in res_text.stdout

    # Test env output
    res_env = subprocess.run(
        [sys.executable, "scripts/generate_demo_tokens.py", "--format", "env"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DEMO_TOKEN_ANALYST=" in res_env.stdout
    assert "DEMO_TOKEN_VP_SUPPLY_CHAIN=" in res_env.stdout
