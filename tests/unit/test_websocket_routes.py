"""Unit tests for WebSocket alert streaming and real-time push (P11-5).

Verifies:
- WebSocket connection lifecycle:
    * Connect to `/ws/alerts` and `/api/v1/ws/alerts` (alias)
    * Bidirectional ping/pong heartbeat
    * Client disconnect handling and resource cleanup
- Authentication & Security:
    * Successful handshake with valid JWT access token query parameter (?token=...)
    * Rejection and socket closure (code 1008 Policy Violation) on invalid or malformed token
    * Rejection on expired JWT token
    * Authenticated user metadata binding to connection session
- Real-time Alert Broadcasting & Multi-client Delivery:
    * Broadcast alert payload to all connected clients
    * Multi-client fanout (multiple concurrent connections receive broadcast)
    * Exact Decimal precision preserved in serialized JSON payload (BR-RULE-001)
    * Canonical NanoCore reference scenario alert broadcast
- Subscription & Filtering Governance:
    * Filtering by risk_level (e.g. CRITICAL, HIGH)
    * Filtering by supplier_id (e.g. SUP-NC-882)
    * Filtering by component_sku (e.g. CMP-MCU-X91)
    * Dynamic in-session subscription updates via `{"type": "subscribe", ...}` messages
- Fault Tolerance & Resilience:
    * Handling abrupt client disconnects during broadcast without disrupting other clients
    * Pruning dead connections automatically
- Integration with Kafka Risk Alert Consumer:
    * Kafka handler message triggers WebSocket broadcast to active subscribers
- WebSocket Stats and Admin Endpoints:
    * GET /api/v1/ws/alerts/stats provides connection counts and subscription metrics
    * POST /api/v1/ws/alerts/broadcast allows programmatic broadcast triggers
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from src.api.main import app
from src.api.routes.websocket_routes import (
    broadcast_risk_alert,
    get_alert_connection_manager,
)
from src.core.security import UserRole, create_access_token
from src.kafka.handlers import persist_risk_alert
from src.kafka.schemas.risk_alert import AlertStatus, RiskAlert, RiskLevel, SpendTier
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

# ------------------------------------------------------------------------------
# Fixtures & Setup
# ------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_connection_manager():
    """Reset the global connection manager before each test."""
    manager = get_alert_connection_manager()
    manager.reset()
    yield manager
    manager.reset()


@pytest.fixture
def valid_analyst_token() -> str:
    """Generate a valid JWT token for an analyst user."""
    return create_access_token(
        subject="usr-analyst-123",
        roles=[UserRole.ANALYST],
        email="analyst@apexmotion.com",
        name="Alex Analyst",
    )


@pytest.fixture
def valid_category_manager_token() -> str:
    """Generate a valid JWT token for a category manager."""
    return create_access_token(
        subject="usr-catmgr-456",
        roles=[UserRole.CATEGORY_MANAGER],
        email="catmgr@apexmotion.com",
        name="Casey Manager",
    )


@pytest.fixture
def expired_token() -> str:
    """Generate an expired JWT token."""
    return create_access_token(
        subject="usr-expired-999",
        roles=[UserRole.ANALYST],
        expires_delta=timedelta(seconds=-3600),
    )


@pytest.fixture
def nanocore_alert_payload() -> dict[str, Any]:
    """Canonical NanoCore golden scenario alert dictionary."""
    return {
        "alert_id": "ALT-NC-001",
        "supplier_id": "SUP-NC-882",
        "component_sku": "CMP-MCU-X91",
        "risk_level": "CRITICAL",
        "days_of_cover": "7.68",
        "gap_days": "1.32",
        "shortage_volume": 24420,
        "financial_exposure": "2448105.00",
        "status": "OPEN",
        "hitl_required": True,
        "hitl_tier": "DUAL_VP",
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ------------------------------------------------------------------------------
# 1. Connection Lifecycle & Handshake Tests
# ------------------------------------------------------------------------------


def test_ws_connection_anonymous_success():
    """Verify client can connect to /ws/alerts anonymously with default settings."""
    client = TestClient(app)
    with client.websocket_connect("/ws/alerts") as ws:
        # Send ping
        ws.send_text(json.dumps({"type": "ping"}))
        response = json.loads(ws.receive_text())
        assert response["type"] == "pong"
        assert "timestamp" in response


def test_ws_connection_alias_route_success():
    """Verify client can connect to the canonical /api/v1/ws/alerts alias."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/alerts") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        response = json.loads(ws.receive_text())
        assert response["type"] == "pong"


def test_ws_connection_with_valid_jwt_token(valid_analyst_token: str):
    """Verify client connects with valid JWT token query param and establishes session."""
    client = TestClient(app)
    with client.websocket_connect(
        f"/ws/alerts?token={valid_analyst_token}&client_id=client-101"
    ) as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        response = json.loads(ws.receive_text())
        assert response["type"] == "pong"
        assert response.get("client_id") == "client-101"

    # Manager tracks the connection while active
    manager = get_alert_connection_manager()
    assert manager.active_connections_count == 0  # decremented on exit


def test_ws_connection_with_invalid_jwt_token_rejected():
    """Verify connection with invalid/tampered JWT token is rejected with 1008 Policy Violation."""
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts?token=invalid.tampered.token"):
            pass
    assert exc_info.value.code == 1008


def test_ws_connection_with_expired_jwt_token_rejected(expired_token: str):
    """Verify connection with expired JWT token is rejected with 1008 Policy Violation."""
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/alerts?token={expired_token}"):
            pass
    assert exc_info.value.code == 1008


# ------------------------------------------------------------------------------
# 2. Ping / Pong and Message Protocol Tests
# ------------------------------------------------------------------------------


def test_ws_ping_pong_protocol():
    """Verify ping message receives pong response with preserved echo data."""
    client = TestClient(app)
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text(json.dumps({"type": "ping", "echo": "seq-42"}))
        response = json.loads(ws.receive_text())
        assert response["type"] == "pong"
        assert response.get("echo") == "seq-42"
        assert "timestamp" in response


def test_ws_invalid_json_message_returns_error():
    """Verify non-JSON message received over WebSocket returns a structured error envelope."""
    client = TestClient(app)
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text("this is not json")
        response = json.loads(ws.receive_text())
        assert response["type"] == "error"
        assert "Invalid JSON" in response["message"]


def test_ws_unknown_message_type_returns_error():
    """Verify unknown message type receives structured error envelope."""
    client = TestClient(app)
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text(json.dumps({"type": "unsupported_action"}))
        response = json.loads(ws.receive_text())
        assert response["type"] == "error"
        assert "Unknown message type" in response["message"]


# ------------------------------------------------------------------------------
# 3. Real-Time Alert Broadcast Tests
# ------------------------------------------------------------------------------


def test_ws_broadcast_alert_to_connected_client(nanocore_alert_payload: dict[str, Any]):
    """Verify connected client receives broadcasted alert payload in real time."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts") as ws:
        # Trigger broadcast via manager
        import asyncio

        asyncio.run(manager.broadcast_alert(nanocore_alert_payload))

        message = json.loads(ws.receive_text())
        assert message["type"] == "risk_alert"
        data = message["data"]
        assert data["alert_id"] == "ALT-NC-001"
        assert data["supplier_id"] == "SUP-NC-882"
        assert data["component_sku"] == "CMP-MCU-X91"
        assert data["risk_level"] == "CRITICAL"
        assert data["days_of_cover"] == "7.68"
        assert data["financial_exposure"] == "2448105.00"
        assert data["hitl_tier"] == "DUAL_VP"


def test_ws_broadcast_to_multiple_clients(nanocore_alert_payload: dict[str, Any]):
    """Verify multiple concurrent WebSocket connections receive identical broadcasts."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts?client_id=client-A") as ws_a:
        with client.websocket_connect("/ws/alerts?client_id=client-B") as ws_b:
            assert manager.active_connections_count == 2

            import asyncio

            asyncio.run(manager.broadcast_alert(nanocore_alert_payload))

            msg_a = json.loads(ws_a.receive_text())
            msg_b = json.loads(ws_b.receive_text())

            assert msg_a["type"] == "risk_alert"
            assert msg_b["type"] == "risk_alert"
            assert msg_a["data"]["alert_id"] == msg_b["data"]["alert_id"] == "ALT-NC-001"


# ------------------------------------------------------------------------------
# 4. Subscription & Filtering Tests
# ------------------------------------------------------------------------------


def test_ws_filter_by_risk_level(nanocore_alert_payload: dict[str, Any]):
    """Verify client filtering by risk_level only receives matching alerts."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    # Client A: subscribes to LOW only
    # Client B: subscribes to CRITICAL only
    with client.websocket_connect("/ws/alerts?risk_level=LOW") as ws_low:
        with client.websocket_connect("/ws/alerts?risk_level=CRITICAL") as ws_crit:
            import asyncio

            # 1. Broadcast CRITICAL NanoCore alert
            asyncio.run(manager.broadcast_alert(nanocore_alert_payload))

            # ws_crit receives it
            msg_crit = json.loads(ws_crit.receive_text())
            assert msg_crit["data"]["risk_level"] == "CRITICAL"

            # ws_low should NOT have received it; verify ping works without queue blockage
            ws_low.send_text(json.dumps({"type": "ping"}))
            msg_low = json.loads(ws_low.receive_text())
            assert msg_low["type"] == "pong"


def test_ws_filter_by_supplier_id(nanocore_alert_payload: dict[str, Any]):
    """Verify client filtering by supplier_id only receives alerts for that supplier."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    # Client target: SUP-NC-882
    # Client other: SUP-OTHER-999
    with client.websocket_connect("/ws/alerts?supplier_id=SUP-NC-882") as ws_target:
        with client.websocket_connect("/ws/alerts?supplier_id=SUP-OTHER-999") as ws_other:
            import asyncio

            asyncio.run(manager.broadcast_alert(nanocore_alert_payload))

            msg_target = json.loads(ws_target.receive_text())
            assert msg_target["data"]["supplier_id"] == "SUP-NC-882"

            ws_other.send_text(json.dumps({"type": "ping"}))
            msg_other = json.loads(ws_other.receive_text())
            assert msg_other["type"] == "pong"


def test_ws_dynamic_subscription_update():
    """Verify client can update subscription filters dynamically during connection."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts?risk_level=LOW") as ws:
        # Dynamically change subscription to CRITICAL
        ws.send_text(
            json.dumps(
                {
                    "type": "subscribe",
                    "risk_level": "CRITICAL",
                    "supplier_id": "SUP-NC-882",
                }
            )
        )
        sub_resp = json.loads(ws.receive_text())
        assert sub_resp["type"] == "subscribed"
        assert "CRITICAL" in sub_resp["filters"]["risk_levels"]
        assert "SUP-NC-882" in sub_resp["filters"]["supplier_ids"]

        # Now broadcast a CRITICAL alert
        import asyncio

        alert = {
            "alert_id": "ALT-DYN-01",
            "supplier_id": "SUP-NC-882",
            "component_sku": "CMP-TEST-01",
            "risk_level": "CRITICAL",
            "financial_exposure": "50000.00",
            "days_of_cover": "3.50",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        asyncio.run(manager.broadcast_alert(alert))

        msg = json.loads(ws.receive_text())
        assert msg["type"] == "risk_alert"
        assert msg["data"]["alert_id"] == "ALT-DYN-01"


# ------------------------------------------------------------------------------
# 5. Fault Tolerance & Dead Connection Pruning
# ------------------------------------------------------------------------------


def test_ws_dead_connection_pruned_on_broadcast(nanocore_alert_payload: dict[str, Any]):
    """Verify abrupt connection failures during broadcast are caught and connection pruned."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts") as ws_healthy:
        assert manager.active_connections_count == 1

        # Simulate a mock dead socket in manager
        mock_dead_ws = AsyncMock()
        mock_dead_ws.send_text.side_effect = RuntimeError("Socket write failed (broken pipe)")
        import asyncio

        asyncio.run(manager.connect(mock_dead_ws, client_id="dead-client"))
        assert manager.active_connections_count == 2

        # Broadcast should succeed for healthy socket and prune dead socket
        asyncio.run(manager.broadcast_alert(nanocore_alert_payload))

        msg = json.loads(ws_healthy.receive_text())
        assert msg["type"] == "risk_alert"
        # Dead socket was pruned
        assert manager.active_connections_count == 1


# ------------------------------------------------------------------------------
# 6. Pydantic RiskAlert Schema and Decimal Serialization Tests
# ------------------------------------------------------------------------------


def test_ws_broadcast_pydantic_risk_alert_schema():
    """Verify broadcasting a Pydantic RiskAlert instance preserves exact Decimal precision."""
    manager = get_alert_connection_manager()
    client = TestClient(app)

    schema_alert = RiskAlert(
        alert_id="ALT-SCHEMA-01",
        supplier_id="SUP-NC-882",
        component_sku="CMP-MCU-X91",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("7.68"),
        gap_days=Decimal("1.32"),
        shortage_volume=24420,
        financial_exposure=Decimal("2448105.00"),
        status=AlertStatus.OPEN,
        hitl_required=True,
        hitl_tier=SpendTier.DUAL_VP,
    )

    with client.websocket_connect("/ws/alerts") as ws:
        import asyncio

        asyncio.run(manager.broadcast_alert(schema_alert))

        msg = json.loads(ws.receive_text())
        data = msg["data"]
        assert data["alert_id"] == "ALT-SCHEMA-01"
        assert data["days_of_cover"] == "7.68"
        assert data["financial_exposure"] == "2448105.00"
        assert data["risk_level"] == "CRITICAL"


# ------------------------------------------------------------------------------
# 7. Helper broadcast_risk_alert Function Test
# ------------------------------------------------------------------------------


def test_helper_broadcast_risk_alert_function(nanocore_alert_payload: dict[str, Any]):
    """Verify standalone helper broadcast_risk_alert dispatches to the global manager."""
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts") as ws:
        import asyncio

        asyncio.run(broadcast_risk_alert(nanocore_alert_payload))

        msg = json.loads(ws.receive_text())
        assert msg["type"] == "risk_alert"
        assert msg["data"]["alert_id"] == "ALT-NC-001"


# ------------------------------------------------------------------------------
# 8. REST Diagnostics & Trigger Endpoints Tests
# ------------------------------------------------------------------------------


def test_ws_stats_endpoint(valid_analyst_token: str):
    """Verify GET /api/v1/ws/alerts/stats returns active connection metrics."""
    client = TestClient(app)

    # Empty stats initially
    resp = client.get(
        "/api/v1/ws/alerts/stats",
        headers={"Authorization": f"Bearer {valid_analyst_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_connections"] == 0

    # With a connected client
    with client.websocket_connect("/ws/alerts?client_id=stats-client&risk_level=CRITICAL"):
        resp = client.get(
            "/api/v1/ws/alerts/stats",
            headers={"Authorization": f"Bearer {valid_analyst_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_connections"] == 1
        assert len(data["subscribers"]) == 1
        assert data["subscribers"][0]["client_id"] == "stats-client"
        assert "CRITICAL" in data["subscribers"][0]["risk_levels"]


def test_ws_rest_broadcast_trigger_endpoint(
    valid_analyst_token: str, nanocore_alert_payload: dict[str, Any]
):
    """Verify POST /api/v1/ws/alerts/broadcast triggers push to connected WebSocket clients."""
    client = TestClient(app)

    with client.websocket_connect("/ws/alerts") as ws:
        # Trigger broadcast via REST
        resp = client.post(
            "/api/v1/ws/alerts/broadcast",
            headers={"Authorization": f"Bearer {valid_analyst_token}"},
            json=nanocore_alert_payload,
        )
        assert resp.status_code == 200
        res_body = resp.json()
        assert res_body["broadcasted"] is True
        assert res_body["recipients"] == 1

        # Check WebSocket received it
        ws_msg = json.loads(ws.receive_text())
        assert ws_msg["type"] == "risk_alert"
        assert ws_msg["data"]["alert_id"] == "ALT-NC-001"


def test_ws_stats_unauthenticated_returns_401():
    """Verify unauthenticated access to /api/v1/ws/alerts/stats returns 401."""
    client = TestClient(app)
    resp = client.get("/api/v1/ws/alerts/stats")
    assert resp.status_code == 401


# ------------------------------------------------------------------------------
# 9. Kafka Event Consumer Handler Integration Test
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kafka_handler_triggers_websocket_broadcast(nanocore_alert_payload: dict[str, Any]):
    """Verify that when persist_risk_alert completes, broadcast_risk_alert is triggered."""
    manager = get_alert_connection_manager()
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()

    await manager.connect(mock_ws, client_id="kafka-listener")

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    mock_persisted = AsyncMock()
    mock_persisted.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    mock_persisted.supplier_id = None
    mock_persisted.component_sku = "CMP-MCU-X91"
    mock_persisted.risk_level = "CRITICAL"
    mock_persisted.days_of_cover = Decimal("7.68")
    mock_persisted.financial_exposure = Decimal("2448105.00")
    mock_persisted.shortage_volume = 24420
    mock_persisted.status = "OPEN"
    mock_persisted.created_at = datetime.now(UTC)
    mock_repo.create.return_value = mock_persisted

    with (
        patch("src.kafka.handlers.RiskAlertRepository", return_value=mock_repo),
        patch("src.kafka.handlers._resolve_supplier_uuid", return_value=None),
    ):
        result = await persist_risk_alert(nanocore_alert_payload, mock_session)
        assert result.component_sku == "CMP-MCU-X91"

        assert mock_ws.send_text.called
        sent_text = mock_ws.send_text.call_args[0][0]
        sent_data = json.loads(sent_text)
        assert sent_data["type"] == "risk_alert"
        assert sent_data["data"]["component_sku"] == "CMP-MCU-X91"
        assert sent_data["data"]["financial_exposure"] == "2448105.00"
