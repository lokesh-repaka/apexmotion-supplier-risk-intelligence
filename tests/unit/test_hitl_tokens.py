"""Unit tests for AWS KMS ECDSA P-256 HITL token service.

Verifies:
- Spend tier determination and time-bound TTL (Category Mgr <= $25k: 1-hr, Director <= $100k: 1-hr, Dual VP > $100k: 30-min)
- Cryptographic ECDSA P-256 token issuance, signing, and verification against AWS KMS
- Strict action ID, alert ID, and monetary amount binding
- Anti-replay detection via SHA-256 token hash lookup
- Dual approval validation for > $100k actions with distinct signer enforcement
- Resilient error handling on expired tokens, tampered signatures, and KMS exceptions
- 100% statement and branch coverage on src/core/hitl_tokens.py
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenError,
    HITLTokenService,
    SpendTier,
    TokenBindingMismatchError,
    TokenExpiredError,
    TokenReplayDetectedError,
    TokenSignatureInvalidError,
    compute_token_hash,
    get_spend_tier,
    get_token_ttl,
)


@pytest.fixture
def mock_kms_client():
    """Mock boto3 KMS client simulating ECDSA P-256 sign and verify operations."""
    client = MagicMock()

    # Default sign response with a dummy 64-byte signature
    client.sign.return_value = {
        "Signature": b"mock_ecdsa_p256_der_signature_bytes_1234567890",
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    # Default verify response
    client.verify.return_value = {
        "SignatureValid": True,
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    return client


@pytest.fixture
def hitl_service(mock_kms_client):
    """Instantiate HITLTokenService with mocked KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


def test_spend_tier_routing_and_ttl():
    """Verify monetary thresholds map to correct spend tiers and TTL limits."""
    # Tier 1: <= $25,000
    assert get_spend_tier(Decimal("1000.00")) == SpendTier.CATEGORY_MGR
    assert get_spend_tier(Decimal("25000.00")) == SpendTier.CATEGORY_MGR
    assert get_token_ttl(SpendTier.CATEGORY_MGR) == timedelta(hours=1)

    # Tier 2: $25,000.01 - $100,000
    assert get_spend_tier(Decimal("25000.01")) == SpendTier.PROC_DIRECTOR
    assert get_spend_tier(Decimal("75000.00")) == SpendTier.PROC_DIRECTOR
    assert get_spend_tier(Decimal("100000.00")) == SpendTier.PROC_DIRECTOR
    assert get_token_ttl(SpendTier.PROC_DIRECTOR) == timedelta(hours=1)

    # Tier 3: > $100,000 (Dual sign-off)
    assert get_spend_tier(Decimal("100000.01")) == SpendTier.DUAL_VP
    assert get_spend_tier(Decimal("2448105.00")) == SpendTier.DUAL_VP
    assert get_token_ttl(SpendTier.DUAL_VP) == timedelta(minutes=30)


def test_issue_and_sign_token_success(hitl_service, mock_kms_client):
    """Verify issuing and signing an ECDSA token binds payload and invokes KMS sign."""
    action_id = "ACT-2026-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("24420.00")

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-cat-mgr-01",
        signer_role="category_manager",
    )

    assert isinstance(token, HITLToken)
    assert token.payload.action_id == action_id
    assert token.payload.alert_id == alert_id
    assert token.payload.amount_usd == amount
    assert token.payload.spend_tier == SpendTier.CATEGORY_MGR
    assert token.payload.signer_id == "usr-cat-mgr-01"
    assert token.signature is not None
    assert len(token.token_hash) == 64

    # Verify KMS sign invocation
    mock_kms_client.sign.assert_called_once()
    call_kwargs = mock_kms_client.sign.call_args[1]
    assert call_kwargs["SigningAlgorithm"] == "ECDSA_SHA_256"
    assert call_kwargs["MessageType"] == "RAW"


def test_verify_valid_token_success(hitl_service, mock_kms_client):
    """Verify that a valid token passes all cryptographic and binding checks."""
    token = hitl_service.issue_token(
        action_id="ACT-GOLDEN-01",
        alert_id="ALT-GOLDEN-01",
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("50000.00"),
        signer_id="usr-dir-01",
        signer_role="procurement_director",
    )

    # Verify with matching constraints
    result = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-GOLDEN-01",
        expected_alert_id="ALT-GOLDEN-01",
        expected_amount_usd=Decimal("50000.00"),
    )

    assert result.is_valid is True
    assert result.error is None
    assert result.payload.action_id == "ACT-GOLDEN-01"
    mock_kms_client.verify.assert_called_once()


def test_verify_token_expired(hitl_service):
    """Verify that expired tokens are rejected with TokenExpiredError."""
    token = hitl_service.issue_token(
        action_id="ACT-EXP-01",
        alert_id="ALT-EXP-01",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("15000.00"),
    )

    # Manually adjust expiration to past
    token.payload.expires_at = datetime.now(UTC) - timedelta(seconds=10)

    # When raise_on_error=True
    with pytest.raises(TokenExpiredError) as exc_info:
        hitl_service.verify_token(token=token, raise_on_error=True)
    assert "expired" in str(exc_info.value).lower()

    # When raise_on_error=False
    result = hitl_service.verify_token(token=token, raise_on_error=False)
    assert result.is_valid is False
    assert result.error == "TOKEN_EXPIRED"


def test_verify_token_tampered_signature(hitl_service, mock_kms_client):
    """Verify that tokens with invalid signatures fail verification."""
    token = hitl_service.issue_token(
        action_id="ACT-TAMPER-01",
        alert_id="ALT-TAMPER-01",
        action_type="INVENTORY_TRANSFER",
        amount_usd=Decimal("5000.00"),
    )

    # Configure KMS mock to report invalid signature
    mock_kms_client.verify.return_value = {"SignatureValid": False}

    with pytest.raises(TokenSignatureInvalidError):
        hitl_service.verify_token(token=token, raise_on_error=True)

    result = hitl_service.verify_token(token=token, raise_on_error=False)
    assert result.is_valid is False
    assert result.error == "INVALID_SIGNATURE"


def test_verify_token_action_id_mismatch(hitl_service):
    """Verify that token evaluated against wrong action ID fails binding check."""
    token = hitl_service.issue_token(
        action_id="ACT-CORRECT",
        alert_id="ALT-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )

    with pytest.raises(TokenBindingMismatchError) as exc_info:
        hitl_service.verify_token(
            token=token,
            expected_action_id="ACT-WRONG",
            raise_on_error=True,
        )
    assert "action_id mismatch" in str(exc_info.value).lower()

    result = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-WRONG",
        raise_on_error=False,
    )
    assert result.is_valid is False
    assert result.error == "ACTION_MISMATCH"


def test_verify_token_alert_id_mismatch(hitl_service):
    """Verify that token evaluated against wrong alert ID fails binding check."""
    token = hitl_service.issue_token(
        action_id="ACT-001",
        alert_id="ALT-CORRECT",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )

    with pytest.raises(TokenBindingMismatchError):
        hitl_service.verify_token(
            token=token,
            expected_alert_id="ALT-WRONG",
            raise_on_error=True,
        )

    result = hitl_service.verify_token(
        token=token,
        expected_alert_id="ALT-WRONG",
        raise_on_error=False,
    )
    assert result.is_valid is False
    assert result.error == "ALERT_MISMATCH"


def test_verify_token_amount_mismatch(hitl_service):
    """Verify that token evaluated against wrong monetary amount fails binding check."""
    token = hitl_service.issue_token(
        action_id="ACT-001",
        alert_id="ALT-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )

    with pytest.raises(TokenBindingMismatchError):
        hitl_service.verify_token(
            token=token,
            expected_amount_usd=Decimal("15000.00"),
            raise_on_error=True,
        )

    result = hitl_service.verify_token(
        token=token,
        expected_amount_usd=Decimal("15000.00"),
        raise_on_error=False,
    )
    assert result.is_valid is False
    assert result.error == "AMOUNT_MISMATCH"


def test_token_serialization_and_deserialization(hitl_service):
    """Verify serialization to string and reconstruction from encoded format."""
    token = hitl_service.issue_token(
        action_id="ACT-SERIAL",
        alert_id="ALT-SERIAL",
        action_type="TEST_ACTION",
        amount_usd=Decimal("30000.00"),
        signer_id="usr-serial",
        signer_role="procurement_director",
    )

    serialized = token.serialize()
    assert isinstance(serialized, str)

    deserialized = HITLToken.deserialize(serialized)
    assert deserialized.payload.action_id == token.payload.action_id
    assert deserialized.payload.amount_usd == token.payload.amount_usd
    assert deserialized.signature == token.signature
    assert deserialized.token_hash == token.token_hash

    # Verify verify_token accepts raw serialized string
    res = hitl_service.verify_token(token=serialized)
    assert res.is_valid is True


def test_token_deserialization_malformed_string():
    """Verify that deserializing invalid strings raises ValueError."""
    for malformed in ["", "not-base64", "!!!", "eyJuYW1lIjogInRlc3QifQ=="]:
        with pytest.raises(ValueError):
            HITLToken.deserialize(malformed)


def test_compute_token_hash_deterministic():
    """Verify compute_token_hash generates stable 64-char hex SHA-256."""
    h1 = compute_token_hash("sample_token_string_1")
    h2 = compute_token_hash("sample_token_string_1")
    h3 = compute_token_hash("sample_token_string_2")

    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


@pytest.mark.asyncio
async def test_anti_replay_detection_with_repository(hitl_service):
    """Verify anti-replay detection rejects tokens whose hash exists in the repository."""
    token = hitl_service.issue_token(
        action_id="ACT-REPLAY",
        alert_id="ALT-REPLAY",
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("12000.00"),
    )

    # 1. Unused token passes
    mock_repo_unused = AsyncMock()
    mock_repo_unused.is_token_used.return_value = False

    result_unused = await hitl_service.verify_anti_replay(
        token=token,
        repository=mock_repo_unused,
    )
    assert result_unused is True

    # 2. Replayed token fails
    mock_repo_used = AsyncMock()
    mock_repo_used.is_token_used.return_value = True

    with pytest.raises(TokenReplayDetectedError):
        await hitl_service.verify_anti_replay(
            token=token,
            repository=mock_repo_used,
            raise_on_error=True,
        )

    result_used = await hitl_service.verify_anti_replay(
        token=token,
        repository=mock_repo_used,
        raise_on_error=False,
    )
    assert result_used is False


def test_dual_approval_verification_success(hitl_service):
    """Verify dual approval validation succeeds with two distinct valid signers."""
    action_id = "ACT-DUAL-001"
    alert_id = "ALT-DUAL-001"
    amount = Decimal("2500000.00")  # > $100k requires dual approval

    token1 = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="EMERGENCY_RESOURCING",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    token2 = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="EMERGENCY_RESOURCING",
        amount_usd=amount,
        signer_id="usr-vp-supply-01",
        signer_role="vp_supply_chain",
    )

    res = hitl_service.verify_dual_approval(
        tokens=[token1, token2],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
    )
    assert res.is_valid is True
    assert res.error is None


def test_dual_approval_insufficient_tokens_rejected(hitl_service):
    """Verify dual approval rejects fewer than 2 tokens."""
    token = hitl_service.issue_token(
        action_id="ACT-01",
        alert_id="ALT-01",
        action_type="EXPEDITE",
        amount_usd=Decimal("150000.00"),
    )

    res_empty = hitl_service.verify_dual_approval(tokens=[])
    assert res_empty.is_valid is False
    assert res_empty.error == "INSUFFICIENT_SIGNATURES"

    res_single = hitl_service.verify_dual_approval(tokens=[token])
    assert res_single.is_valid is False
    assert res_single.error == "INSUFFICIENT_SIGNATURES"


def test_dual_approval_same_signer_rejected(hitl_service):
    """Verify dual approval rejects tokens signed by the same individual."""
    token1 = hitl_service.issue_token(
        action_id="ACT-SAME",
        alert_id="ALT-SAME",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-director-01",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-SAME",
        alert_id="ALT-SAME",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-director-01",  # Same signer!
    )

    res = hitl_service.verify_dual_approval(tokens=[token1, token2])
    assert res.is_valid is False
    assert res.error == "IDENTICAL_SIGNERS"


def test_dual_approval_action_mismatch_rejected(hitl_service):
    """Verify dual approval rejects tokens with conflicting action IDs."""
    token1 = hitl_service.issue_token(
        action_id="ACT-A",
        alert_id="ALT-SAME",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-1",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-B",
        alert_id="ALT-SAME",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-2",
    )

    res = hitl_service.verify_dual_approval(tokens=[token1, token2])
    assert res.is_valid is False
    assert res.error == "DUAL_ACTION_MISMATCH"


def test_kms_client_exception_handling(hitl_service, mock_kms_client):
    """Verify KMS ClientError exceptions are caught and raised as TokenSignatureInvalidError."""
    # Test sign failure
    mock_kms_client.sign.side_effect = ClientError(
        {"Error": {"Code": "KMSInternalException", "Message": "KMS unavailable"}},
        "Sign",
    )

    with pytest.raises(TokenSignatureInvalidError) as exc_sign:
        hitl_service.issue_token(
            action_id="ACT-FAIL",
            alert_id="ALT-FAIL",
            action_type="TEST",
            amount_usd=Decimal("1000.00"),
        )
    assert "kms signing failed" in str(exc_sign.value).lower()

    # Reset sign and test verify failure
    mock_kms_client.sign.side_effect = None
    mock_kms_client.verify.side_effect = ClientError(
        {"Error": {"Code": "KMSInvalidSignatureException", "Message": "Signature bad"}},
        "Verify",
    )

    token = hitl_service.issue_token(
        action_id="ACT-FAIL",
        alert_id="ALT-FAIL",
        action_type="TEST",
        amount_usd=Decimal("1000.00"),
    )

    res = hitl_service.verify_token(token=token, raise_on_error=False)
    assert res.is_valid is False
    assert res.error == "INVALID_SIGNATURE"


def test_service_client_initialization_defaults():
    """Verify service defaults initialize properly when no custom client passed."""
    service = HITLTokenService()
    assert service.key_arn is not None
    client = service._get_client()
    assert client is not None


def test_verify_token_malformed_string_coverage(hitl_service):
    """Verify verify_token with malformed serialized string returns error or raises."""
    res = hitl_service.verify_token("invalid_base64_string", raise_on_error=False)
    assert res.is_valid is False
    assert res.error == "MALFORMED_TOKEN"

    with pytest.raises(HITLTokenError):
        hitl_service.verify_token("invalid_base64_string", raise_on_error=True)


def test_dual_approval_with_serialized_strings_and_invalid_token(hitl_service):
    """Verify verify_dual_approval handles serialized strings and detects invalid token."""
    token1 = hitl_service.issue_token(
        action_id="ACT-DUAL-STR",
        alert_id="ALT-01",
        action_type="TEST",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-1",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-DUAL-STR",
        alert_id="ALT-01",
        action_type="TEST",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-2",
    )

    # Pass as serialized strings
    s1 = token1.serialize()
    s2 = token2.serialize()

    res_ok = hitl_service.verify_dual_approval(tokens=[s1, s2])
    assert res_ok.is_valid is True

    # One token expired
    token2.payload.expires_at = datetime.now(UTC) - timedelta(seconds=10)
    s2_expired = token2.serialize()

    res_fail = hitl_service.verify_dual_approval(tokens=[s1, s2_expired])
    assert res_fail.is_valid is False
    assert res_fail.error == "TOKEN_EXPIRED"
