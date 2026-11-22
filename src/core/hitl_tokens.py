"""AWS KMS ECDSA P-256 Human-in-the-Loop (HITL) approval token service.

Enforces:
- Cryptographic ECDSA P-256 signatures via AWS KMS (ECC_NIST_P256, ECDSA_SHA_256)
- Monetary spend tier governance (Category Mgr <= $25k, Director <= $100k, Dual VP > $100k)
- Time-bound TTL (1 hour for single approval <= $100k; 30 minutes for dual approval > $100k)
- Immutable cryptographic binding to action ID, alert ID, and exact authorized amount
- SHA-256 token hashing for anti-replay verification at the database level
- Dual sign-off enforcement for high-value (> $100k) consequential actions
"""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("apexmotion.hitl_tokens")


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class HITLTokenError(Exception):
    """Base exception for HITL token operations."""


class TokenExpiredError(HITLTokenError):
    """Raised when an approval token has exceeded its TTL."""


class TokenSignatureInvalidError(HITLTokenError):
    """Raised when KMS ECDSA signature verification fails or signing fails."""


class TokenBindingMismatchError(HITLTokenError):
    """Raised when token action, alert, or amount does not match expected parameters."""


class TokenReplayDetectedError(HITLTokenError):
    """Raised when a cryptographic token has already been consumed (replay attack)."""


# ------------------------------------------------------------------------------
# Spend Tiers & TTL Governance (CLAUDE.md Section 3 & BR-RULE-001)
# ------------------------------------------------------------------------------


class SpendTier(StrEnum):
    """Spend authority tiers determining required signers and TTL limits."""

    CATEGORY_MGR = "CATEGORY_MGR"  # Spend <= $25,000 (1x token, 1-hr TTL)
    PROC_DIRECTOR = "PROC_DIRECTOR"  # Spend $25,001 - $100,000 (1x token, 1-hr TTL)
    DUAL_VP = "DUAL_VP"  # Spend > $100,000 (Dual sign-off, 30-min TTL)


def get_spend_tier(amount_usd: Decimal) -> SpendTier:
    """Determine the governing spend tier for an authorized commitment amount.

    Enforces Decimal monetary precision to comply with BR-RULE-001.
    """
    settings = get_settings()
    if amount_usd <= settings.HITL_TIER_1_THRESHOLD_USD:
        return SpendTier.CATEGORY_MGR
    if amount_usd <= settings.HITL_TIER_2_THRESHOLD_USD:
        return SpendTier.PROC_DIRECTOR
    return SpendTier.DUAL_VP


def get_token_ttl(spend_tier: SpendTier) -> timedelta:
    """Return the time-to-live limit for an approval token based on spend tier."""
    if spend_tier == SpendTier.DUAL_VP:
        return timedelta(minutes=30)
    return timedelta(hours=1)


# ------------------------------------------------------------------------------
# Token Payload & Canonical Serialization
# ------------------------------------------------------------------------------


class HITLTokenPayload(BaseModel):
    """Cryptographic domain payload for an authorized HITL spend action."""

    action_id: str = Field(description="Unique action commitment identifier")
    alert_id: str = Field(description="Associated risk alert UUID")
    action_type: str = Field(description="Mitigation action type (e.g. LOGISTICS_EXPEDITE)")
    amount_usd: Decimal = Field(description="Authorized monetary commitment in USD")
    spend_tier: SpendTier = Field(description="Governing spend authority tier")
    issued_at: datetime = Field(description="UTC timestamp when token was minted")
    expires_at: datetime = Field(description="UTC timestamp when token expires")
    nonce: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique random cryptographic nonce",
    )
    signer_id: str | None = Field(default=None, description="User ID of authorized signer")
    signer_role: str | None = Field(default=None, description="RBAC role of authorized signer")

    def canonical_bytes(self) -> bytes:
        """Serialize payload into deterministic, canonical JSON bytes for KMS signing."""
        canonical_dict: dict[str, Any] = {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "alert_id": self.alert_id,
            "amount_usd": f"{self.amount_usd:.2f}",
            "expires_at": self.expires_at.astimezone(UTC).isoformat(),
            "issued_at": self.issued_at.astimezone(UTC).isoformat(),
            "nonce": self.nonce,
            "signer_id": self.signer_id or "",
            "signer_role": self.signer_role or "",
            "spend_tier": self.spend_tier.value,
        }
        json_str = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        return json_str.encode("utf-8")


# ------------------------------------------------------------------------------
# Token Representation & Verification Results
# ------------------------------------------------------------------------------


def compute_token_hash(token: str | bytes) -> str:
    """Compute the SHA-256 hexadecimal digest of a serialized token for anti-replay."""
    data = token.encode("utf-8") if isinstance(token, str) else token
    return hashlib.sha256(data).hexdigest()


class TokenVerificationResult(BaseModel):
    """Result of cryptographic and semantic token verification."""

    is_valid: bool
    error: str | None = None
    payload: HITLTokenPayload | None = None
    token_hash: str | None = None


class HITLToken(BaseModel):
    """Complete Human-in-the-Loop approval token with payload, signature, and metadata."""

    payload: HITLTokenPayload
    signature: str = Field(description="Base64-encoded raw ECDSA P-256 signature from KMS")
    key_arn: str = Field(description="KMS Key ARN used for signing")
    token_hash: str = Field(description="SHA-256 hash of the complete serialized token")

    def serialize(self) -> str:
        """Serialize the token into a URL-safe Base64 encoded string."""
        raw_dict = {
            "payload": self.payload.model_dump(mode="json"),
            "signature": self.signature,
            "key_arn": self.key_arn,
        }
        json_bytes = json.dumps(raw_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("utf-8")

    @classmethod
    def deserialize(cls, serialized: str) -> "HITLToken":
        """Reconstruct a HITLToken from its URL-safe Base64 serialized form."""
        try:
            json_bytes = base64.urlsafe_b64decode(serialized.strip().encode("utf-8"))
            data = json.loads(json_bytes.decode("utf-8"))
            payload = HITLTokenPayload(**data["payload"])
            signature = str(data["signature"])
            key_arn = str(data["key_arn"])
            token_hash = compute_token_hash(serialized)
            return cls(
                payload=payload,
                signature=signature,
                key_arn=key_arn,
                token_hash=token_hash,
            )
        except Exception as exc:
            raise ValueError(f"Malformed or invalid serialized HITL token: {exc}") from exc


# ------------------------------------------------------------------------------
# HITL Token Service
# ------------------------------------------------------------------------------


class HITLTokenService:
    """Service governing issuance, cryptographic KMS signing, and verification of HITL tokens."""

    def __init__(
        self,
        kms_client: Any | None = None,
        key_arn: str | None = None,
    ) -> None:
        self.settings = get_settings()
        self.key_arn = key_arn or self.settings.KMS_KEY_ARN
        self._kms_client = kms_client

    def _get_client(self) -> Any:
        """Lazily initialize boto3 KMS client if not injected."""
        if self._kms_client is None:
            self._kms_client = boto3.client(
                "kms",
                region_name=self.settings.AWS_REGION,
            )
        return self._kms_client

    def issue_token(
        self,
        action_id: str,
        alert_id: str,
        action_type: str,
        amount_usd: Decimal,
        signer_id: str | None = None,
        signer_role: str | None = None,
    ) -> HITLToken:
        """Mint, sign with KMS ECDSA P-256, and return a cryptographically bound HITL token."""
        now = datetime.now(UTC)
        spend_tier = get_spend_tier(amount_usd)
        ttl = get_token_ttl(spend_tier)
        expires_at = now + ttl

        payload = HITLTokenPayload(
            action_id=action_id,
            alert_id=alert_id,
            action_type=action_type,
            amount_usd=amount_usd,
            spend_tier=spend_tier,
            issued_at=now,
            expires_at=expires_at,
            signer_id=signer_id,
            signer_role=signer_role,
        )

        canonical_data = payload.canonical_bytes()
        client = self._get_client()

        try:
            sign_resp = client.sign(
                KeyId=self.key_arn,
                Message=canonical_data,
                MessageType="RAW",
                SigningAlgorithm="ECDSA_SHA_256",
            )
            raw_sig: bytes = sign_resp["Signature"]
            b64_sig = base64.b64encode(raw_sig).decode("utf-8")
        except ClientError as exc:
            logger.error("AWS KMS signing failure for action '%s': %s", action_id, exc)
            raise TokenSignatureInvalidError(f"KMS signing failed: {exc}") from exc

        # Create temporary token to compute canonical hash
        temp_token = HITLToken(
            payload=payload,
            signature=b64_sig,
            key_arn=self.key_arn,
            token_hash="",
        )
        serialized = temp_token.serialize()
        token_hash = compute_token_hash(serialized)
        temp_token.token_hash = token_hash

        logger.info(
            "Issued HITL token for action '%s' (Tier: %s, TTL: %ds, Hash: %s...)",
            action_id,
            spend_tier.value,
            int(ttl.total_seconds()),
            token_hash[:16],
        )
        return temp_token

    def verify_token(
        self,
        token: str | HITLToken,
        expected_action_id: str | None = None,
        expected_alert_id: str | None = None,
        expected_amount_usd: Decimal | None = None,
        raise_on_error: bool = False,
    ) -> TokenVerificationResult:
        """Verify an ECDSA token signature, temporal TTL, and parameter bindings against AWS KMS."""
        # 1. Parse token if serialized string
        if isinstance(token, str):
            try:
                hitl_token = HITLToken.deserialize(token)
            except ValueError as exc:
                logger.warning("Token verification failed: malformed encoding: %s", exc)
                if raise_on_error:
                    raise HITLTokenError(str(exc)) from exc
                return TokenVerificationResult(is_valid=False, error="MALFORMED_TOKEN")
        else:
            hitl_token = token

        payload = hitl_token.payload
        token_hash = hitl_token.token_hash

        # 2. Check temporal validity (TTL expiration)
        now = datetime.now(UTC)
        if now > payload.expires_at:
            logger.warning(
                "Token verification failed: token expired at %s (current: %s)",
                payload.expires_at.isoformat(),
                now.isoformat(),
            )
            if raise_on_error:
                raise TokenExpiredError(f"Token has expired at {payload.expires_at.isoformat()}.")
            return TokenVerificationResult(
                is_valid=False,
                error="TOKEN_EXPIRED",
                payload=payload,
                token_hash=token_hash,
            )

        # 3. Verify parameter bindings
        if expected_action_id is not None and payload.action_id != expected_action_id:
            logger.warning(
                "Token verification failed: action_id mismatch (expected '%s', got '%s')",
                expected_action_id,
                payload.action_id,
            )
            if raise_on_error:
                raise TokenBindingMismatchError(
                    f"Action_id mismatch: expected '{expected_action_id}', got '{payload.action_id}'."
                )
            return TokenVerificationResult(
                is_valid=False,
                error="ACTION_MISMATCH",
                payload=payload,
                token_hash=token_hash,
            )

        if expected_alert_id is not None and payload.alert_id != expected_alert_id:
            logger.warning(
                "Token verification failed: alert_id mismatch (expected '%s', got '%s')",
                expected_alert_id,
                payload.alert_id,
            )
            if raise_on_error:
                raise TokenBindingMismatchError(
                    f"Alert_id mismatch: expected '{expected_alert_id}', got '{payload.alert_id}'."
                )
            return TokenVerificationResult(
                is_valid=False,
                error="ALERT_MISMATCH",
                payload=payload,
                token_hash=token_hash,
            )

        if expected_amount_usd is not None and payload.amount_usd != expected_amount_usd:
            logger.warning(
                "Token verification failed: amount mismatch (expected %s, got %s)",
                expected_amount_usd,
                payload.amount_usd,
            )
            if raise_on_error:
                raise TokenBindingMismatchError(
                    f"Amount mismatch: expected {expected_amount_usd}, got {payload.amount_usd}."
                )
            return TokenVerificationResult(
                is_valid=False,
                error="AMOUNT_MISMATCH",
                payload=payload,
                token_hash=token_hash,
            )

        # 4. Cryptographically verify signature via AWS KMS
        client = self._get_client()
        canonical_data = payload.canonical_bytes()
        raw_sig = base64.b64decode(hitl_token.signature.encode("utf-8"))

        try:
            verify_resp = client.verify(
                KeyId=hitl_token.key_arn,
                Message=canonical_data,
                MessageType="RAW",
                Signature=raw_sig,
                SigningAlgorithm="ECDSA_SHA_256",
            )
            is_valid_sig = bool(verify_resp.get("SignatureValid", False))
        except ClientError as exc:
            logger.error("AWS KMS signature verification error: %s", exc)
            is_valid_sig = False

        if not is_valid_sig:
            logger.warning(
                "Token verification failed: cryptographic signature invalid for action '%s'",
                payload.action_id,
            )
            if raise_on_error:
                raise TokenSignatureInvalidError(
                    "Cryptographic ECDSA signature verification failed."
                )
            return TokenVerificationResult(
                is_valid=False,
                error="INVALID_SIGNATURE",
                payload=payload,
                token_hash=token_hash,
            )

        logger.info(
            "Token verification successful for action '%s' (Hash: %s...)",
            payload.action_id,
            token_hash[:16],
        )
        return TokenVerificationResult(
            is_valid=True,
            payload=payload,
            token_hash=token_hash,
        )

    async def verify_anti_replay(
        self,
        token: str | HITLToken,
        repository: Any,
        raise_on_error: bool = False,
    ) -> bool:
        """Verify that the token hash has not already been used in previous actions."""
        token_hash = token.token_hash if isinstance(token, HITLToken) else compute_token_hash(token)
        is_used = await repository.is_token_used(token_hash)

        if is_used:
            logger.error(
                "SECURITY ALERT: Cryptographic token replay detected for hash: %s", token_hash
            )
            if raise_on_error:
                raise TokenReplayDetectedError(
                    f"Token replay detected: hash {token_hash} has already been registered."
                )
            return False

        return True

    def verify_dual_approval(
        self,
        tokens: list[str | HITLToken],
        expected_action_id: str | None = None,
        expected_alert_id: str | None = None,
        expected_amount_usd: Decimal | None = None,
    ) -> TokenVerificationResult:
        """Verify dual sign-off requirements for high-value commitments (> $100,000).

        Requires two independently signed tokens with distinct signers bound to the same action.
        """
        if len(tokens) < 2:
            logger.warning("Dual approval failed: received %d token(s), required 2", len(tokens))
            return TokenVerificationResult(
                is_valid=False,
                error="INSUFFICIENT_SIGNATURES",
            )

        parsed_tokens: list[HITLToken] = []
        for t in tokens:
            if isinstance(t, str):
                parsed = HITLToken.deserialize(t)
            else:
                parsed = t
            parsed_tokens.append(parsed)

        # Check all tokens are individually valid
        for p in parsed_tokens:
            res = self.verify_token(
                token=p,
                expected_action_id=expected_action_id,
                expected_alert_id=expected_alert_id,
                expected_amount_usd=expected_amount_usd,
                raise_on_error=False,
            )
            if not res.is_valid:
                return res

        # Check distinct signers
        signers = {p.payload.signer_id for p in parsed_tokens if p.payload.signer_id}
        if len(signers) < 2:
            logger.warning(
                "Dual approval failed: identical signers or missing signer ID: %s", signers
            )
            return TokenVerificationResult(
                is_valid=False,
                error="IDENTICAL_SIGNERS",
            )

        # Check matching action IDs
        action_ids = {p.payload.action_id for p in parsed_tokens}
        if len(action_ids) > 1:
            logger.warning(
                "Dual approval failed: tokens bound to different actions: %s", action_ids
            )
            return TokenVerificationResult(
                is_valid=False,
                error="DUAL_ACTION_MISMATCH",
            )

        logger.info(
            "Dual approval verified successfully for action '%s' with signers: %s",
            parsed_tokens[0].payload.action_id,
            signers,
        )
        return TokenVerificationResult(
            is_valid=True,
            payload=parsed_tokens[0].payload,
        )
