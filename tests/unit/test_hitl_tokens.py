"""Unit tests for AWS KMS ECDSA P-256 HITL token service (P14-2, P4-2, P10-4).

Verifies the core acceptance criteria specified in TASKS.md and CLAUDE.md:
1. Valid Token:
   - Tier 1 (CATEGORY_MGR <= $25k, 1-hr TTL): single signature validates, binds payload, and approves.
   - Tier 2 (PROC_DIRECTOR $25k-$100k, 1-hr TTL): single signature validates, binds payload, and approves.
   - Tier 3 (DUAL_VP > $100k, 30-min TTL): dual distinct signatures (Director + VP) validate and approve.
   - Strict boundary threshold mappings ($25,000.00 vs $25,000.01; $100,000.00 vs $100,000.01).
   - Canonical bytes determinism and sorted key ordering.
2. Expired TTL:
   - Token rejected when current time exceeds expires_at (TokenExpiredError / TOKEN_EXPIRED).
   - Boundary tests: 1-hour TTL for Tier 1/2, 30-minute TTL for Tier 3.
   - Rejection in single-token and dual-approval workflows (1st or 2nd token expired).
3. Replay Detection:
   - Anti-replay verification via compute_token_hash(token) (SHA-256).
   - Replay detected when token hash has already been registered in the database repository.
   - Token hash uniqueness across identical action payloads via cryptographic nonces.
   - Anti-replay tampering defense: altering token string changes hash but invalidates KMS signature.
4. Wrong Action Binding & Parameter Mismatches:
   - Action ID mismatch rejected with TokenBindingMismatchError / ACTION_MISMATCH.
   - Alert ID mismatch rejected with TokenBindingMismatchError / ALERT_MISMATCH.
   - Authorized Amount mismatch rejected with TokenBindingMismatchError / AMOUNT_MISMATCH.
   - Cross-action, cross-alert, and cross-amount binding mismatches in dual approval.
5. Missing Second Signature & Multi-Signer Governance:
   - Tier 3 action submitted with 0 tokens: rejected with INSUFFICIENT_SIGNATURES.
   - Tier 3 action submitted with only 1 token: rejected with INSUFFICIENT_SIGNATURES.
   - Tier 3 action submitted with 2 tokens from identical signer: rejected with IDENTICAL_SIGNERS.
   - Tier 3 action submitted with missing signer ID: rejected with IDENTICAL_SIGNERS.
   - Tier 3 action with 2 tokens where 2nd token has invalid signature: rejected with INVALID_SIGNATURE.
   - Invariant verified: A DUAL_VP action proceeding with only one approval signature must NEVER happen.
6. KMS Exceptions & Serialization Robustness:
   - ClientError during sign/verify caught and handled gracefully.
   - Malformed base64 and corrupted JSON handling.
- 100% statement and branch coverage on src/core/hitl_tokens.py.
"""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenError,
    HITLTokenPayload,
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
def mock_kms_client() -> MagicMock:
    """Mock boto3 KMS client simulating ECDSA P-256 sign and verify operations."""
    client = MagicMock()

    # Default sign response with dummy signature bytes
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
def hitl_service(mock_kms_client: MagicMock) -> HITLTokenService:
    """Instantiate HITLTokenService with mocked KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


# ------------------------------------------------------------------------------
# 1. Spend Tier Routing & Monetary Threshold Tests
# ------------------------------------------------------------------------------


def test_spend_tier_routing_and_ttl() -> None:
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


def test_valid_token_boundary_thresholds() -> None:
    """Verify exact penny boundary thresholds for spend tiers."""
    # $25,000.00 vs $25,000.01
    assert get_spend_tier(Decimal("25000.00")) == SpendTier.CATEGORY_MGR
    assert get_spend_tier(Decimal("25000.01")) == SpendTier.PROC_DIRECTOR

    # $100,000.00 vs $100,000.01
    assert get_spend_tier(Decimal("100000.00")) == SpendTier.PROC_DIRECTOR
    assert get_spend_tier(Decimal("100000.01")) == SpendTier.DUAL_VP


# ------------------------------------------------------------------------------
# 2. Valid Token Issuance & Verification Tests
# ------------------------------------------------------------------------------


def test_issue_and_sign_token_success(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
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


def test_verify_valid_token_success(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
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
    assert result.payload is not None
    assert result.payload.action_id == "ACT-GOLDEN-01"
    assert result.token_hash == token.token_hash
    mock_kms_client.verify.assert_called_once()


def test_valid_token_category_manager_tier_1(hitl_service: HITLTokenService) -> None:
    """Verify Tier 1 token (<= $25k) binds 1-hr TTL and Category Manager metadata."""
    token = hitl_service.issue_token(
        action_id="ACT-TIER-1",
        alert_id="ALT-001",
        action_type="SPOT_BUY",
        amount_usd=Decimal("15000.00"),
        signer_id="usr-cat-01",
        signer_role="category_manager",
    )
    assert token.payload.spend_tier == SpendTier.CATEGORY_MGR
    duration = token.payload.expires_at - token.payload.issued_at
    assert duration == timedelta(hours=1)

    res = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-TIER-1",
        expected_alert_id="ALT-001",
        expected_amount_usd=Decimal("15000.00"),
    )
    assert res.is_valid is True


def test_valid_token_procurement_director_tier_2(hitl_service: HITLTokenService) -> None:
    """Verify Tier 2 token ($25k-$100k) binds 1-hr TTL and Director metadata."""
    token = hitl_service.issue_token(
        action_id="ACT-TIER-2",
        alert_id="ALT-002",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("75000.00"),
        signer_id="usr-dir-01",
        signer_role="procurement_director",
    )
    assert token.payload.spend_tier == SpendTier.PROC_DIRECTOR
    duration = token.payload.expires_at - token.payload.issued_at
    assert duration == timedelta(hours=1)

    res = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-TIER-2",
        expected_alert_id="ALT-002",
        expected_amount_usd=Decimal("75000.00"),
    )
    assert res.is_valid is True


def test_valid_token_dual_vp_tier_3(hitl_service: HITLTokenService) -> None:
    """Verify Tier 3 token (> $100k, NanoCore $2,448,105.00) binds 30-min TTL and Dual VP tier."""
    token = hitl_service.issue_token(
        action_id="ACT-NANOCORE-01",
        alert_id="ALT-NC-001",
        action_type="EMERGENCY_RESOURCING",
        amount_usd=Decimal("2448105.00"),
        signer_id="usr-vp-01",
        signer_role="vp_supply_chain",
    )
    assert token.payload.spend_tier == SpendTier.DUAL_VP
    duration = token.payload.expires_at - token.payload.issued_at
    assert duration == timedelta(minutes=30)

    res = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-NANOCORE-01",
        expected_alert_id="ALT-NC-001",
        expected_amount_usd=Decimal("2448105.00"),
    )
    assert res.is_valid is True


def test_valid_token_canonical_bytes_determinism() -> None:
    """Verify that canonical_bytes() serializes JSON with deterministic sorted keys."""
    now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    exp = now + timedelta(hours=1)

    payload = HITLTokenPayload(
        action_id="ACT-CANON-01",
        alert_id="ALT-CANON-01",
        action_type="TRANSFER",
        amount_usd=Decimal("25000.00"),
        spend_tier=SpendTier.CATEGORY_MGR,
        issued_at=now,
        expires_at=exp,
        nonce="test-nonce-12345",
        signer_id="usr-01",
        signer_role="category_manager",
    )

    canonical = payload.canonical_bytes()
    expected_dict = {
        "action_id": "ACT-CANON-01",
        "action_type": "TRANSFER",
        "alert_id": "ALT-CANON-01",
        "amount_usd": "25000.00",
        "expires_at": exp.isoformat(),
        "issued_at": now.isoformat(),
        "nonce": "test-nonce-12345",
        "signer_id": "usr-01",
        "signer_role": "category_manager",
        "spend_tier": "CATEGORY_MGR",
    }
    expected_bytes = json.dumps(expected_dict, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    assert canonical == expected_bytes


# ------------------------------------------------------------------------------
# 3. Expired TTL Tests
# ------------------------------------------------------------------------------


def test_verify_token_expired(hitl_service: HITLTokenService) -> None:
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


def test_expired_ttl_tier_1_boundary(hitl_service: HITLTokenService) -> None:
    """Verify Tier 1 1-hour TTL temporal boundary."""
    token = hitl_service.issue_token(
        action_id="ACT-EXP-T1",
        alert_id="ALT-EXP-T1",
        action_type="EXPEDITE",
        amount_usd=Decimal("20000.00"),
    )

    # 1 second before expiration: valid
    token.payload.expires_at = datetime.now(UTC) + timedelta(seconds=2)
    assert hitl_service.verify_token(token=token).is_valid is True

    # 1 second past expiration: expired
    token.payload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    res = hitl_service.verify_token(token=token)
    assert res.is_valid is False
    assert res.error == "TOKEN_EXPIRED"


def test_expired_ttl_tier_3_boundary(hitl_service: HITLTokenService) -> None:
    """Verify Tier 3 30-minute TTL temporal boundary."""
    token = hitl_service.issue_token(
        action_id="ACT-EXP-T3",
        alert_id="ALT-EXP-T3",
        action_type="EMERGENCY_RESOURCING",
        amount_usd=Decimal("250000.00"),
    )

    token.payload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    res = hitl_service.verify_token(token=token)
    assert res.is_valid is False
    assert res.error == "TOKEN_EXPIRED"


def test_expired_token_in_dual_approval_second_token(hitl_service: HITLTokenService) -> None:
    """Verify dual approval fails when the 2nd token has expired."""
    t1 = hitl_service.issue_token(
        action_id="ACT-DUAL-EXP",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("200000.00"),
        signer_id="usr-1",
    )
    t2 = hitl_service.issue_token(
        action_id="ACT-DUAL-EXP",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("200000.00"),
        signer_id="usr-2",
    )

    t2.payload.expires_at = datetime.now(UTC) - timedelta(seconds=5)

    res = hitl_service.verify_dual_approval(tokens=[t1, t2])
    assert res.is_valid is False
    assert res.error == "TOKEN_EXPIRED"


# ------------------------------------------------------------------------------
# 4. Tampered Signature & KMS Exceptions
# ------------------------------------------------------------------------------


def test_verify_token_tampered_signature(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
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


def test_kms_client_exception_handling(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
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


# ------------------------------------------------------------------------------
# 5. Wrong Action Binding & Parameter Mismatches
# ------------------------------------------------------------------------------


def test_verify_token_action_id_mismatch(hitl_service: HITLTokenService) -> None:
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


def test_verify_token_alert_id_mismatch(hitl_service: HITLTokenService) -> None:
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


def test_verify_token_amount_mismatch(hitl_service: HITLTokenService) -> None:
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


def test_wrong_action_binding_mismatches_all_fields(hitl_service: HITLTokenService) -> None:
    """Verify comprehensive binding rejections across action, alert, and amount simultaneously."""
    token = hitl_service.issue_token(
        action_id="ACT-TRUE-01",
        alert_id="ALT-TRUE-01",
        action_type="EXPEDITE",
        amount_usd=Decimal("50000.00"),
    )

    # 1. Action mismatch takes precedence
    res_act = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-FALSE",
        expected_alert_id="ALT-FALSE",
        expected_amount_usd=Decimal("10000.00"),
    )
    assert res_act.is_valid is False
    assert res_act.error == "ACTION_MISMATCH"

    # 2. Alert mismatch when action matches
    res_alt = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-TRUE-01",
        expected_alert_id="ALT-FALSE",
        expected_amount_usd=Decimal("10000.00"),
    )
    assert res_alt.is_valid is False
    assert res_alt.error == "ALERT_MISMATCH"

    # 3. Amount mismatch when action & alert match
    res_amt = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-TRUE-01",
        expected_alert_id="ALT-TRUE-01",
        expected_amount_usd=Decimal("50000.01"),
    )
    assert res_amt.is_valid is False
    assert res_amt.error == "AMOUNT_MISMATCH"


# ------------------------------------------------------------------------------
# 6. Anti-Replay Detection & Token Hashing
# ------------------------------------------------------------------------------


def test_compute_token_hash_deterministic() -> None:
    """Verify compute_token_hash generates stable 64-char hex SHA-256."""
    h1 = compute_token_hash("sample_token_string_1")
    h2 = compute_token_hash("sample_token_string_1")
    h3 = compute_token_hash("sample_token_string_2")

    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


def test_anti_replay_hash_uniqueness_across_nonces(hitl_service: HITLTokenService) -> None:
    """Verify two tokens for the identical action receive distinct nonces and unique hashes."""
    t1 = hitl_service.issue_token(
        action_id="ACT-IDENTICAL",
        alert_id="ALT-IDENTICAL",
        action_type="EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )
    t2 = hitl_service.issue_token(
        action_id="ACT-IDENTICAL",
        alert_id="ALT-IDENTICAL",
        action_type="EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )

    assert t1.payload.nonce != t2.payload.nonce
    assert t1.token_hash != t2.token_hash


@pytest.mark.asyncio
async def test_anti_replay_detection_with_repository(hitl_service: HITLTokenService) -> None:
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


@pytest.mark.asyncio
async def test_anti_replay_with_raw_string(hitl_service: HITLTokenService) -> None:
    """Verify anti-replay works when passing raw serialized token string."""
    token = hitl_service.issue_token(
        action_id="ACT-STR-REPLAY",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )
    raw_str = token.serialize()

    mock_repo = AsyncMock()
    mock_repo.is_token_used.return_value = True

    with pytest.raises(TokenReplayDetectedError):
        await hitl_service.verify_anti_replay(
            token=raw_str, repository=mock_repo, raise_on_error=True
        )


def test_anti_replay_tampered_payload_hash_divergence(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
    """Verify that altering token string payload changes token_hash but fails KMS signature check."""
    token = hitl_service.issue_token(
        action_id="ACT-ORIGINAL",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )
    original_str = token.serialize()
    orig_hash = compute_token_hash(original_str)

    # Decode, tamper action_id, re-encode
    raw_json = base64.urlsafe_b64decode(original_str.encode("utf-8")).decode("utf-8")
    data = json.loads(raw_json)
    data["payload"]["action_id"] = "ACT-TAMPERED"
    tampered_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tampered_str = base64.urlsafe_b64encode(tampered_bytes).decode("utf-8")

    tampered_hash = compute_token_hash(tampered_str)
    assert orig_hash != tampered_hash

    # Configure KMS mock to reject tampered message signature
    mock_kms_client.verify.return_value = {"SignatureValid": False}

    # Verification must fail on signature
    res = hitl_service.verify_token(token=tampered_str)
    assert res.is_valid is False
    assert res.error == "INVALID_SIGNATURE"


# ------------------------------------------------------------------------------
# 7. Dual Approval & Multi-Signer Governance Tests
# ------------------------------------------------------------------------------


def test_dual_approval_verification_success(hitl_service: HITLTokenService) -> None:
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


def test_dual_approval_insufficient_tokens_rejected(hitl_service: HITLTokenService) -> None:
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


def test_dual_approval_same_signer_rejected(hitl_service: HITLTokenService) -> None:
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


def test_dual_approval_missing_signer_id_rejected(hitl_service: HITLTokenService) -> None:
    """Verify dual approval rejects tokens when signer_id is None."""
    token1 = hitl_service.issue_token(
        action_id="ACT-NOSIGNER",
        alert_id="ALT-001",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id=None,
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-NOSIGNER",
        alert_id="ALT-001",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-vp-01",
    )

    res = hitl_service.verify_dual_approval(tokens=[token1, token2])
    assert res.is_valid is False
    assert res.error == "IDENTICAL_SIGNERS"


def test_dual_approval_action_mismatch_rejected(hitl_service: HITLTokenService) -> None:
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


def test_dual_approval_alert_mismatch_rejected(hitl_service: HITLTokenService) -> None:
    """Verify dual approval rejects when tokens are bound to conflicting alert IDs."""
    token1 = hitl_service.issue_token(
        action_id="ACT-SHARED",
        alert_id="ALT-001",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-1",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-SHARED",
        alert_id="ALT-002",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-2",
    )

    # When expected_alert_id is ALT-001, token2 fails alert match
    res = hitl_service.verify_dual_approval(
        tokens=[token1, token2],
        expected_alert_id="ALT-001",
    )
    assert res.is_valid is False
    assert res.error == "ALERT_MISMATCH"


def test_dual_approval_amount_mismatch_rejected(hitl_service: HITLTokenService) -> None:
    """Verify dual approval rejects when one token has an authorized amount mismatch."""
    token1 = hitl_service.issue_token(
        action_id="ACT-AMT",
        alert_id="ALT-001",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-1",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-AMT",
        alert_id="ALT-001",
        action_type="AIR_FREIGHT",
        amount_usd=Decimal("120000.00"),  # Different amount
        signer_id="usr-2",
    )

    res = hitl_service.verify_dual_approval(
        tokens=[token1, token2],
        expected_amount_usd=Decimal("150000.00"),
    )
    assert res.is_valid is False
    assert res.error == "AMOUNT_MISMATCH"


def test_dual_approval_second_token_invalid_signature_rejected(
    hitl_service: HITLTokenService, mock_kms_client: MagicMock
) -> None:
    """Verify dual approval rejects when the second token's KMS signature is invalid."""
    token1 = hitl_service.issue_token(
        action_id="ACT-SIG-TEST",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-1",
    )
    token2 = hitl_service.issue_token(
        action_id="ACT-SIG-TEST",
        alert_id="ALT-001",
        action_type="EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-2",
    )

    # 1st verify succeeds, 2nd fails
    mock_kms_client.verify.side_effect = [
        {"SignatureValid": True},
        {"SignatureValid": False},
    ]

    res = hitl_service.verify_dual_approval(tokens=[token1, token2])
    assert res.is_valid is False
    assert res.error == "INVALID_SIGNATURE"


def test_dual_approval_three_distinct_signers_success(hitl_service: HITLTokenService) -> None:
    """Verify dual approval accepts 3 distinct valid executive signatures."""
    tokens = [
        hitl_service.issue_token(
            action_id="ACT-THREE",
            alert_id="ALT-001",
            action_type="EXPEDITE",
            amount_usd=Decimal("500000.00"),
            signer_id=f"usr-exec-{i}",
        )
        for i in range(1, 4)
    ]

    res = hitl_service.verify_dual_approval(tokens=tokens, expected_action_id="ACT-THREE")
    assert res.is_valid is True
    assert res.error is None


# ------------------------------------------------------------------------------
# 8. Token Serialization & Malformed Encoding
# ------------------------------------------------------------------------------


def test_token_serialization_and_deserialization(hitl_service: HITLTokenService) -> None:
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


def test_token_deserialization_malformed_string() -> None:
    """Verify that deserializing invalid strings raises ValueError."""
    for malformed in ["", "not-base64", "!!!", "eyJuYW1lIjogInRlc3QifQ=="]:
        with pytest.raises(ValueError):
            HITLToken.deserialize(malformed)


def test_verify_token_malformed_string_coverage(hitl_service: HITLTokenService) -> None:
    """Verify verify_token with malformed serialized string returns error or raises."""
    res = hitl_service.verify_token("invalid_base64_string", raise_on_error=False)
    assert res.is_valid is False
    assert res.error == "MALFORMED_TOKEN"

    with pytest.raises(HITLTokenError):
        hitl_service.verify_token("invalid_base64_string", raise_on_error=True)


def test_service_client_initialization_defaults() -> None:
    """Verify service defaults initialize properly when no custom client passed."""
    service = HITLTokenService()
    assert service.key_arn is not None
    client = service._get_client()
    assert client is not None


def test_dual_approval_with_serialized_strings_and_invalid_token(
    hitl_service: HITLTokenService,
) -> None:
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
