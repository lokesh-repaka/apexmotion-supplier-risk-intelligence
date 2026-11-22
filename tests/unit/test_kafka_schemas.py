"""Unit tests for Kafka Event Schemas (src/kafka/schemas/).

Verifies:
- SupplierEvent schema validation, severity levels, and payload serialization.
- RiskAlert schema validation, Decimal monetary precision, and NanoCore golden scenario.
- HITLRequest schema validation, spend tier consistency, and dual sign-off requirements.
- AuditEvent schema validation, append-only invariants, and PII/credential redaction.
- BaseEvent JSON schema generation and Pydantic v2 strictness (extra='forbid').
- 100% offline isolation with zero external I/O.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from src.kafka.schemas import (
    AlertStatus,
    AuditEvent,
    AuditEventSchema,
    DisruptionType,
    HITLActionType,
    HITLRequest,
    HITLRequestEvent,
    HITLStatus,
    RiskAlert,
    RiskAlertEvent,
    RiskLevel,
    SeverityLevel,
    SpendTier,
    SupplierEvent,
)

# ==============================================================================
# SupplierEvent Tests
# ==============================================================================


def test_supplier_event_valid_creation():
    """Verify SupplierEvent creates successfully with valid disruption attributes."""
    event = SupplierEvent(
        event_id="EVT-2026-001",
        event_type=DisruptionType.NEWS_DISRUPTION,
        supplier_id="SUP-NC-882",
        source="REUTERS",
        severity=SeverityLevel.CRITICAL,
        description="Cleanroom fire detected at Hsinchu fabrication plant.",
        affected_skus=["CMP-MCU-X91"],
        metadata={"region": "APAC", "facility": "FAB-2"},
        trace_id="trc-supplier-event-001",
    )

    assert event.event_id == "EVT-2026-001"
    assert event.event_type == DisruptionType.NEWS_DISRUPTION
    assert event.supplier_id == "SUP-NC-882"
    assert event.severity == SeverityLevel.CRITICAL
    assert event.affected_skus == ["CMP-MCU-X91"]
    assert event.metadata["facility"] == "FAB-2"
    assert event.trace_id == "trc-supplier-event-001"
    assert isinstance(event.timestamp, datetime)
    assert event.schema_version == "1.0"


def test_supplier_event_nanocore_golden_scenario():
    """Verify SupplierEvent accurately represents canonical NanoCore Cleanroom fire."""
    event = SupplierEvent(
        event_id="EVT-NEWS-2026-081",
        event_type=DisruptionType.NEWS_DISRUPTION,
        supplier_id="SUP-NC-882",
        source="GLOBAL_NEWS_WIRE",
        severity=SeverityLevel.CRITICAL,
        description="Cleanroom fire at Hsinchu packaging facility disrupting MCU-X91 wafer allocation.",
        affected_skus=["CMP-MCU-X91"],
    )

    data = event.to_dict()
    assert data["event_id"] == "EVT-NEWS-2026-081"
    assert data["supplier_id"] == "SUP-NC-882"
    assert data["affected_skus"] == ["CMP-MCU-X91"]
    assert data["severity"] == "CRITICAL"


def test_supplier_event_empty_fields_rejected():
    """Verify SupplierEvent rejects empty event_id, supplier_id, or source."""
    with pytest.raises(ValidationError):
        SupplierEvent(
            event_id="",  # Empty event ID rejected
            event_type=DisruptionType.NEWS_DISRUPTION,
            supplier_id="SUP-NC-882",
            source="REUTERS",
            severity=SeverityLevel.HIGH,
            description="Valid description",
        )

    with pytest.raises(ValidationError):
        SupplierEvent(
            event_id="EVT-001",
            event_type=DisruptionType.NEWS_DISRUPTION,
            supplier_id="   ",  # Blank supplier ID rejected
            source="REUTERS",
            severity=SeverityLevel.HIGH,
            description="Valid description",
        )


def test_supplier_event_invalid_severity_rejected():
    """Verify SupplierEvent rejects invalid severity strings."""
    with pytest.raises(ValidationError):
        SupplierEvent(
            event_id="EVT-001",
            event_type=DisruptionType.NEWS_DISRUPTION,
            supplier_id="SUP-NC-882",
            source="REUTERS",
            severity="CATASTROPHIC",  # Invalid severity enum
            description="Valid description",
        )


def test_supplier_event_serialization_roundtrip():
    """Verify SupplierEvent JSON serialization and deserialization roundtrip."""
    original = SupplierEvent(
        event_id="EVT-ROUNDTRIP-01",
        event_type=DisruptionType.WEATHER_ALERT,
        supplier_id="SUP-BE-101",
        source="METEO_RADAR",
        severity=SeverityLevel.MEDIUM,
        description="Typhoon warning near Kaohsiung port.",
        affected_skus=["CMP-PMIC-440"],
    )

    json_str = original.to_json()
    bytes_data = original.to_bytes()
    assert isinstance(json_str, str)
    assert isinstance(bytes_data, bytes)

    reconstructed = SupplierEvent.from_json(json_str)
    assert reconstructed.event_id == original.event_id
    assert reconstructed.supplier_id == original.supplier_id
    assert reconstructed.severity == original.severity
    assert reconstructed.affected_skus == original.affected_skus


# ==============================================================================
# RiskAlert Tests
# ==============================================================================


def test_risk_alert_nanocore_golden_scenario():
    """Verify RiskAlert validates exact NanoCore golden metrics with Decimal precision."""
    alert = RiskAlert(
        alert_id="ALT-2026-NANOCORE",
        supplier_id="SUP-NC-882",
        component_sku="CMP-MCU-X91",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("7.68"),
        gap_days=Decimal("1.32"),
        shortage_volume=24420,
        financial_exposure=Decimal("2448105.00"),
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.0"),
        hitl_required=True,
        hitl_tier=SpendTier.PROC_DIRECTOR,
        trace_id="trc-nanocore-alert",
    )

    assert alert.days_of_cover == Decimal("7.68")
    assert alert.gap_days == Decimal("1.32")
    assert alert.shortage_volume == 24420
    assert alert.financial_exposure == Decimal("2448105.00")
    assert alert.risk_level == RiskLevel.CRITICAL
    assert alert.status == AlertStatus.OPEN
    assert alert.hitl_tier == SpendTier.PROC_DIRECTOR

    # Verify JSON serialization preserves Decimal precision as string
    json_data = json.loads(alert.to_json())
    assert json_data["days_of_cover"] == "7.68"
    assert json_data["gap_days"] == "1.32"
    assert json_data["financial_exposure"] == "2448105.00"
    assert json_data["shortage_volume"] == 24420


def test_risk_alert_alias_equivalence():
    """Verify RiskAlert and RiskAlertEvent refer to the exact same schema class."""
    assert RiskAlert is RiskAlertEvent


def test_risk_alert_negative_numbers_rejected():
    """Verify RiskAlert rejects negative days_of_cover, financial_exposure, and shortage_volume."""
    with pytest.raises(ValidationError):
        RiskAlert(
            alert_id="ALT-NEG-01",
            supplier_id="SUP-NC-882",
            component_sku="CMP-MCU-X91",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("-1.5"),  # Negative rejected
            financial_exposure=Decimal("10000.00"),
            shortage_volume=100,
        )

    with pytest.raises(ValidationError):
        RiskAlert(
            alert_id="ALT-NEG-02",
            supplier_id="SUP-NC-882",
            component_sku="CMP-MCU-X91",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("5.0"),
            financial_exposure=Decimal("-500.00"),  # Negative rejected
            shortage_volume=100,
        )

    with pytest.raises(ValidationError):
        RiskAlert(
            alert_id="ALT-NEG-03",
            supplier_id="SUP-NC-882",
            component_sku="CMP-MCU-X91",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("5.0"),
            financial_exposure=Decimal("500.00"),
            shortage_volume=-10,  # Negative rejected
        )


def test_risk_alert_auto_derives_hitl_required():
    """Verify hitl_required defaults to True for CRITICAL or HIGH risk levels."""
    alert_critical = RiskAlert(
        alert_id="ALT-AUTO-01",
        supplier_id="SUP-NC-882",
        component_sku="CMP-MCU-X91",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("2.0"),
        financial_exposure=Decimal("1000000.00"),
        shortage_volume=5000,
    )
    assert alert_critical.hitl_required is True

    alert_low = RiskAlert(
        alert_id="ALT-AUTO-02",
        supplier_id="SUP-NC-882",
        component_sku="CMP-MCU-X91",
        risk_level=RiskLevel.LOW,
        days_of_cover=Decimal("45.0"),
        financial_exposure=Decimal("0.00"),
        shortage_volume=0,
    )
    assert alert_low.hitl_required is False


# ==============================================================================
# HITLRequest Tests
# ==============================================================================


def test_hitl_request_category_mgr_tier():
    """Verify HITLRequest validates Category Manager tier (<= $25,000, 1 signer)."""
    now = datetime.now(UTC)
    request = HITLRequest(
        action_id="ACT-CAT-01",
        alert_id="ALT-001",
        supplier_id="SUP-NC-882",
        action_type=HITLActionType.BUFFER_REALLOCATION,
        amount_usd=Decimal("25000.00"),
        spend_tier=SpendTier.CATEGORY_MGR,
        required_signers_count=1,
        expires_at=now + timedelta(hours=1),
        created_at=now,
    )

    assert request.spend_tier == SpendTier.CATEGORY_MGR
    assert request.required_signers_count == 1
    assert request.amount_usd == Decimal("25000.00")
    assert request.status == HITLStatus.PENDING


def test_hitl_request_proc_director_tier():
    """Verify HITLRequest validates Procurement Director tier ($25,001 - $100,000, 1 signer)."""
    now = datetime.now(UTC)
    request = HITLRequest(
        action_id="ACT-DIR-01",
        alert_id="ALT-002",
        supplier_id="SUP-NC-882",
        action_type=HITLActionType.LOGISTICS_EXPEDITE,
        amount_usd=Decimal("75000.00"),
        spend_tier=SpendTier.PROC_DIRECTOR,
        required_signers_count=1,
        expires_at=now + timedelta(hours=1),
        created_at=now,
    )

    assert request.spend_tier == SpendTier.PROC_DIRECTOR
    assert request.required_signers_count == 1
    assert request.amount_usd == Decimal("75000.00")


def test_hitl_request_dual_vp_tier():
    """Verify HITLRequest validates Dual VP tier (> $100,000, 2 signers required)."""
    now = datetime.now(UTC)
    request = HITLRequest(
        action_id="ACT-VP-01",
        alert_id="ALT-003",
        supplier_id="SUP-NC-882",
        action_type=HITLActionType.SECONDARY_SOURCE_SPOT_BUY,
        amount_usd=Decimal("2448105.00"),
        spend_tier=SpendTier.DUAL_VP,
        required_signers_count=2,
        expires_at=now + timedelta(minutes=30),
        created_at=now,
    )

    assert request.spend_tier == SpendTier.DUAL_VP
    assert request.required_signers_count == 2
    assert request.amount_usd == Decimal("2448105.00")


def test_hitl_request_alias_equivalence():
    """Verify HITLRequest and HITLRequestEvent refer to the exact same schema class."""
    assert HITLRequest is HITLRequestEvent


def test_hitl_request_inconsistent_tier_amount_rejected():
    """Verify HITLRequest rejects mismatch between amount_usd and spend_tier."""
    now = datetime.now(UTC)
    # $150,000 cannot be CATEGORY_MGR
    with pytest.raises(ValidationError):
        HITLRequest(
            action_id="ACT-BAD-01",
            alert_id="ALT-001",
            supplier_id="SUP-NC-882",
            action_type=HITLActionType.LOGISTICS_EXPEDITE,
            amount_usd=Decimal("150000.00"),
            spend_tier=SpendTier.CATEGORY_MGR,  # Inconsistent!
            required_signers_count=1,
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )

    # $150,000 cannot have only 1 required signer
    with pytest.raises(ValidationError):
        HITLRequest(
            action_id="ACT-BAD-02",
            alert_id="ALT-001",
            supplier_id="SUP-NC-882",
            action_type=HITLActionType.LOGISTICS_EXPEDITE,
            amount_usd=Decimal("150000.00"),
            spend_tier=SpendTier.DUAL_VP,
            required_signers_count=1,  # Must be 2 for DUAL_VP!
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )


def test_hitl_request_expiration_before_creation_rejected():
    """Verify HITLRequest rejects expires_at <= created_at."""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        HITLRequest(
            action_id="ACT-EXPIRED-01",
            alert_id="ALT-001",
            supplier_id="SUP-NC-882",
            action_type=HITLActionType.LOGISTICS_EXPEDITE,
            amount_usd=Decimal("20000.00"),
            spend_tier=SpendTier.CATEGORY_MGR,
            required_signers_count=1,
            created_at=now,
            expires_at=now - timedelta(minutes=10),  # In the past!
        )


# ==============================================================================
# AuditEvent Tests
# ==============================================================================


def test_audit_event_valid_creation():
    """Verify AuditEvent creates successfully with complete forensic audit details."""
    event = AuditEvent(
        event_id="AUD-2026-001",
        entity_type="risk_alert",
        entity_id="ALT-2026-NANOCORE",
        action="RISK_CALCULATION",
        actor_id="sys-engine",
        actor_role="system",
        before_state={"status": "PENDING"},
        after_state={"status": "INVESTIGATING", "exposure": "2448105.00"},
        trace_id="trc-audit-001",
    )

    assert event.event_id == "AUD-2026-001"
    assert event.entity_type == "risk_alert"
    assert event.action == "RISK_CALCULATION"
    assert event.actor_id == "sys-engine"
    assert event.actor_role == "system"
    assert event.trace_id == "trc-audit-001"


def test_audit_event_alias_equivalence():
    """Verify AuditEvent and AuditEventSchema refer to the exact same schema class."""
    assert AuditEvent is AuditEventSchema


def test_audit_event_credential_redaction():
    """Verify AuditEvent automatically sanitizes credentials from before_state and after_state."""
    event = AuditEvent(
        event_id="AUD-REDACT-01",
        entity_type="hitl_approval",
        entity_id="ACT-999",
        action="SIGN_APPROVAL",
        actor_id="usr-elena-rostova",
        actor_role="vp_supply_chain",
        before_state={"user": "elena", "password": "super-secret-password"},
        after_state={
            "token": "eyJhbGciOiJSUzI1NiJ9.secret-token",
            "kms_key": "arn:aws:kms:secret-key",
            "status": "APPROVED",
        },
    )

    assert event.before_state["password"] == "[REDACTED]"
    assert event.after_state["token"] == "[REDACTED]"
    assert event.after_state["kms_key"] == "[REDACTED]"
    assert event.after_state["status"] == "APPROVED"


def test_audit_event_empty_identifiers_rejected():
    """Verify AuditEvent rejects empty event_id, entity_id, or action."""
    with pytest.raises(ValidationError):
        AuditEvent(
            event_id="",  # Empty event_id
            entity_type="risk_alert",
            entity_id="ALT-100",
            action="CREATE",
            actor_id="sys-engine",
        )

    with pytest.raises(ValidationError):
        AuditEvent(
            event_id="AUD-002",
            entity_type="",  # Empty entity_type
            entity_id="ALT-100",
            action="CREATE",
            actor_id="sys-engine",
        )


# ==============================================================================
# BaseEvent & Pydantic Strictness Tests
# ==============================================================================


def test_extra_fields_forbidden():
    """Verify Pydantic models reject unexpected extra fields (extra='forbid')."""
    with pytest.raises(ValidationError):
        SupplierEvent(
            event_id="EVT-EXTRA",
            event_type=DisruptionType.NEWS_DISRUPTION,
            supplier_id="SUP-NC-882",
            source="REUTERS",
            severity=SeverityLevel.HIGH,
            description="Valid",
            malicious_injected_field="attack_payload",  # Forbidden extra field!
        )


def test_string_whitespace_stripped():
    """Verify Pydantic models automatically strip leading and trailing whitespace."""
    event = SupplierEvent(
        event_id="  EVT-STRIPPED-01  ",
        event_type=DisruptionType.NEWS_DISRUPTION,
        supplier_id="  SUP-NC-882  ",
        source="  REUTERS  ",
        severity=SeverityLevel.HIGH,
        description="  Clean text  ",
    )

    assert event.event_id == "EVT-STRIPPED-01"
    assert event.supplier_id == "SUP-NC-882"
    assert event.source == "REUTERS"
    assert event.description == "Clean text"


def test_json_schema_export_all_schemas():
    """Verify all 4 event schemas export valid JSON schemas for Kafka Schema Registry."""
    supplier_schema = SupplierEvent.model_json_schema()
    risk_alert_schema = RiskAlert.model_json_schema()
    hitl_schema = HITLRequest.model_json_schema()
    audit_schema = AuditEvent.model_json_schema()

    assert supplier_schema["title"] == "SupplierEvent"
    assert "event_id" in supplier_schema["properties"]

    assert risk_alert_schema["title"] == "RiskAlert"
    assert "financial_exposure" in risk_alert_schema["properties"]

    assert hitl_schema["title"] == "HITLRequest"
    assert "spend_tier" in hitl_schema["properties"]

    assert audit_schema["title"] == "AuditEvent"
    assert "entity_type" in audit_schema["properties"]


def test_base_event_naive_datetime_and_bytes_deserialization():
    """Verify BaseEvent handles naive datetimes and bytes deserialization."""
    naive_dt = datetime(2026, 11, 22, 10, 30, 0)
    event = SupplierEvent(
        event_id="EVT-NAIVE-01",
        event_type=DisruptionType.NEWS_DISRUPTION,
        supplier_id="SUP-1",
        source="FEED",
        severity=SeverityLevel.LOW,
        description="Text",
        timestamp=naive_dt,
    )
    json_bytes = event.to_bytes()
    reconstructed = SupplierEvent.from_json(json_bytes)
    assert reconstructed.event_id == "EVT-NAIVE-01"
    assert reconstructed.timestamp.tzinfo is not None


def test_audit_event_list_payload_sanitization_and_blank_validation():
    """Verify recursive list redaction and blank field rejection in AuditEvent."""
    event = AuditEvent(
        event_id="AUD-LIST-01",
        entity_type="supplier",
        entity_id="SUP-1",
        action="UPDATE",
        actor_id="usr-1",
        before_state={"items": [{"api_key": "secret123", "name": "val"}]},
    )
    assert event.before_state["items"][0]["api_key"] == "[REDACTED]"

    with pytest.raises(ValidationError):
        AuditEvent(
            event_id="AUD-BAD",
            entity_type="supplier",
            entity_id="SUP-1",
            action="   ",  # Blank action
            actor_id="usr-1",
        )


def test_hitl_request_naive_datetime_and_blank_validation():
    """Verify naive datetime handling and blank string rejection in HITLRequest."""
    naive_now = datetime(2026, 11, 22, 10, 0, 0)
    naive_exp = datetime(2026, 11, 22, 11, 0, 0)
    req = HITLRequest(
        action_id="ACT-NAIVE",
        alert_id="ALT-1",
        supplier_id="SUP-1",
        action_type=HITLActionType.BUFFER_REALLOCATION,
        amount_usd=Decimal("10000.00"),
        spend_tier=SpendTier.CATEGORY_MGR,
        created_at=naive_now,
        expires_at=naive_exp,
    )
    assert req.created_at.tzinfo is not None

    with pytest.raises(ValidationError):
        HITLRequest(
            action_id="   ",  # Blank action_id
            alert_id="ALT-1",
            supplier_id="SUP-1",
            action_type=HITLActionType.BUFFER_REALLOCATION,
            amount_usd=Decimal("10000.00"),
            spend_tier=SpendTier.CATEGORY_MGR,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )


def test_risk_alert_blank_validation_and_none_decimal():
    """Verify blank validation and None Decimal serialization in RiskAlert."""
    alert = RiskAlert(
        alert_id="ALT-NONE-01",
        supplier_id="SUP-1",
        component_sku="CMP-1",
        risk_level=RiskLevel.LOW,
        days_of_cover=Decimal("10.0"),
        gap_days=None,
    )
    assert alert.gap_days is None
    data = alert.to_dict()
    assert data["gap_days"] is None

    with pytest.raises(ValidationError):
        RiskAlert(
            alert_id="ALT-BAD",
            supplier_id="SUP-1",
            component_sku="   ",  # Blank component_sku
            risk_level=RiskLevel.LOW,
            days_of_cover=Decimal("10.0"),
        )


def test_supplier_event_blank_description_rejected():
    """Verify blank description is rejected in SupplierEvent."""
    with pytest.raises(ValidationError):
        SupplierEvent(
            event_id="EVT-1",
            event_type=DisruptionType.NEWS_DISRUPTION,
            supplier_id="SUP-1",
            source="FEED",
            severity=SeverityLevel.LOW,
            description="   ",  # Blank description
        )


def test_hitl_request_to_json_serializes_amount():
    """Verify HITLRequest serializes Decimal amount to string in JSON."""
    now = datetime.now(UTC)
    req = HITLRequest(
        action_id="ACT-SERIAL",
        alert_id="ALT-1",
        supplier_id="SUP-1",
        action_type=HITLActionType.LOGISTICS_EXPEDITE,
        amount_usd=Decimal("50000.00"),
        spend_tier=SpendTier.PROC_DIRECTOR,
        expires_at=now + timedelta(hours=1),
    )
    json_data = json.loads(req.to_json())
    assert json_data["amount_usd"] == "50000.00"


def test_risk_alert_invalid_risk_level_rejected():
    """Verify RiskAlert rejects invalid risk_level string."""
    with pytest.raises(ValidationError):
        RiskAlert(
            alert_id="ALT-INVALID-LEVEL",
            supplier_id="SUP-1",
            component_sku="CMP-1",
            risk_level="INVALID_EXTREME_LEVEL",
            days_of_cover=Decimal("10.0"),
        )
