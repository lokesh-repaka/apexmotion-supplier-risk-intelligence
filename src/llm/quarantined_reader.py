"""Quarantined Reader Component for ApexMotion Supplier Risk Intelligence Platform.

Module: src.llm.quarantined_reader
Implements:
- Layering Invariants (CLAUDE.md Sec 5.2 & Sec 8.1): Sanitizes all untrusted external text
  (supplier contracts, news articles, SEC filings, supplier emails) before inclusion
  in any LLM prompt.
- Strips non-printable ASCII control characters and HTML/XML tags.
- Tag-breakout defense: Neutralizes closing and opening delimiter tags in content.
- Prompt injection detection, adversarial directive redaction, and risk scoring (LLD Sec 5.2).
- Token budget enforcement and clean truncation with explicit indicator.
- Cryptographic SHA-256 content hashing of raw and sanitized payloads.
- Passive XML structural encapsulation in `<untrusted_supplier_data>`.
- Autonomous forensic audit trail recording in `audit_logs` (BR-RULE-007).
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from litellm.utils import token_counter

from src.core.audit import write_audit_log
from src.core.logging import get_logger, get_trace_id
from src.core.telemetry import trace_span
from src.guardrails.input_sanitizer import (
    InputSanitizer,
    get_input_sanitizer,
)

logger = get_logger("apexmotion.llm.quarantined_reader")

# ------------------------------------------------------------------------------
# Constants & Defaults
# ------------------------------------------------------------------------------

DEFAULT_MAX_TOKENS = 8000
DEFAULT_FALLBACK_MODEL = "claude-3-5-sonnet-20241022"

# Non-printable ASCII control characters: null (0x00) through backspace (0x08),
# vertical tab (0x0B), form feed (0x0C), shift out (0x0E) through unit separator (0x1F), and DEL (0x7F).
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Dangerous script and style blocks containing executable or formatting injections
SCRIPT_STYLE_BLOCKS_REGEX = re.compile(
    r"<(script|style|xml|\?xml|!DOCTYPE)[^>]*>[\s\S]*?(</\1>|$)",
    re.IGNORECASE,
)

# General HTML/XML tags
HTML_TAGS_REGEX = re.compile(r"<[^>]+>")

# Delimiter breakout tag defense (strips attempts to close or re-open sandbox tags)
DELIMITER_BREAKOUT_REGEX = re.compile(
    r"<\/?(untrusted_supplier_data|untrusted_signal|system|instructions|prompt|admin)[^>]*>",
    re.IGNORECASE,
)

# High-risk adversarial prompt injection directives (LLD Sec 5.2)
INJECTION_DIRECTIVES_REGEX = re.compile(
    r"("
    r"ignore\s+(all\s+)?prior\s+instructions|"
    r"disregard\s+(all\s+)?(previous|prior)\s+(prompts?|instructions?)|"
    r"you\s+are\s+now\s+(a\s+|an\s+)?[a-z0-9_-]+|"
    r"system\s+override|"
    r"bypass\s+all\s+rules|"
    r"drop\s+table|"
    r"reveal\s+(all\s+)?system\s+prompts?|"
    r"dan\s+mode|"
    r"jailbreak|"
    r"switch\s+to\s+developer\s+mode|"
    r"pretend\s+you\s+are|"
    r"you\s+must\s+now\s+obey|"
    r"output\s+all\s+confidential|"
    r"<script[\s\S]*?>"
    r")",
    re.IGNORECASE,
)


# ------------------------------------------------------------------------------
# Data Models & Domain Exceptions
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SanitizedPayload:
    """Immutable data container holding the results of quarantined text sanitization."""

    sanitized_text: str
    inner_text: str
    raw_hash: str
    content_hash: str
    injection_score: float
    is_safe: bool
    token_count: int
    is_truncated: bool
    source_id: str
    audit_logged: bool = False

    def __str__(self) -> str:
        """Return the encapsulated sanitized text for seamless prompt formatting."""
        return self.sanitized_text


class PromptInjectionDetectedError(Exception):
    """Raised in strict mode when untrusted text contains prompt injection directives (RFC 7807)."""

    def __init__(
        self,
        message: str = "Input payload contained blacklisted instruction sequences. Text has been quarantined.",
        injection_score: float = 0.0,
        payload: SanitizedPayload | None = None,
        result: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = 422
        self.error_code = "SEC_422_INJECTION"
        self.injection_score = injection_score
        self.payload = payload
        self.result = result


# ------------------------------------------------------------------------------
# Token Counting & Truncation Helpers
# ------------------------------------------------------------------------------


def _count_tokens(text: str, model: str = DEFAULT_FALLBACK_MODEL) -> int:
    """Count tokens offline using litellm token_counter with character fallback."""
    if not text:
        return 0
    try:
        return token_counter(model=model, text=text)
    except Exception:
        # Offline heuristic fallback: ~4 characters per token
        return max(1, len(text) // 4)


def _truncate_to_token_budget(
    text: str,
    max_tokens: int,
    model: str = DEFAULT_FALLBACK_MODEL,
) -> tuple[str, int, bool]:
    """Truncate text to enforce token budget, appending a clear truncation notice."""
    initial_tokens = _count_tokens(text, model=model)
    if initial_tokens <= max_tokens:
        return text, initial_tokens, False

    # Binary search character cut point to fit within max_tokens
    notice = f"\n[TRUNCATED: Exceeded max token budget of {max_tokens} tokens]"
    notice_tokens = _count_tokens(notice, model=model)
    target_budget = max(1, max_tokens - notice_tokens)

    low = 0
    high = len(text)
    best_cut = 0

    while low <= high:
        mid = (low + high) // 2
        slice_candidate = text[:mid]
        tokens = _count_tokens(slice_candidate, model=model)

        if tokens <= target_budget:
            best_cut = mid
            low = mid + 1
        else:
            high = mid - 1

    truncated_text = text[:best_cut].rstrip() + notice
    final_tokens = _count_tokens(truncated_text, model=model)
    return truncated_text, final_tokens, True


# ------------------------------------------------------------------------------
# Core QuarantinedReader Service
# ------------------------------------------------------------------------------


class QuarantinedReader:
    """Isolates, sanitizes, and encapsulates untrusted external text payloads before LLM ingestion."""

    def __init__(
        self,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
        model: str = DEFAULT_FALLBACK_MODEL,
        sanitizer: InputSanitizer | None = None,
    ) -> None:
        self.default_max_tokens = default_max_tokens
        self.model = model
        self.sanitizer = sanitizer or get_input_sanitizer()

    def sanitize(
        self,
        raw_text: str,
        source_id: str = "unknown",
        max_tokens: int | None = None,
        wrap_tags: bool = True,
        raise_on_injection: bool = False,
    ) -> SanitizedPayload:
        """Sanitize an untrusted text payload synchronously.

        Steps:
        1. Strips non-printable ASCII control and invisible/bidi Unicode characters.
        2. Normalizes fullwidth characters via NFKC and unwraps CDATA/comments.
        3. Strips HTML/XML tags and delimiter breakout attempts to preserve quarantine.
        4. Neutralizes dangerous markdown executable links and images.
        5. Detects prompt injection signatures (with homoglyph normalization), scores, and redacts.
        6. Enforces max token budget and truncates if necessary.
        7. Computes SHA-256 hashes of raw and sanitized text.
        8. Enforces passive XML structural encapsulation in `<untrusted_supplier_data>`.
        """
        budget = max_tokens if max_tokens is not None else self.default_max_tokens
        raw_hash = hashlib.sha256((raw_text or "").encode("utf-8")).hexdigest()

        with trace_span(
            "quarantined_reader.sanitize",
            attributes={"input.chars": len(raw_text or ""), "source_id": source_id},
        ) as span:
            if not raw_text or not raw_text.strip():
                empty_hash = hashlib.sha256(b"").hexdigest()
                wrapped = (
                    f'<untrusted_supplier_data source="{source_id}" safe="true" hash="{empty_hash}">\n'
                    f"</untrusted_supplier_data>"
                    if wrap_tags
                    else ""
                )
                span.set_attribute("injection.score", 0.0)
                span.set_attribute("is_safe", True)
                span.set_attribute("is_truncated", False)
                return SanitizedPayload(
                    sanitized_text=wrapped,
                    inner_text="",
                    raw_hash=raw_hash,
                    content_hash=empty_hash,
                    injection_score=0.0,
                    is_safe=True,
                    token_count=0,
                    is_truncated=False,
                    source_id=source_id,
                    audit_logged=False,
                )

            # 1-4: Delegate deep sanitization to InputSanitizer guardrail
            sanitization_result = self.sanitizer.sanitize(
                raw_text=raw_text, raise_on_injection=False
            )
            cleaned_body = sanitization_result.cleaned_text
            injection_score = sanitization_result.injection_score
            is_safe = sanitization_result.is_safe

            # 5. Enforce max token budget
            truncated_body, token_count, is_truncated = _truncate_to_token_budget(
                cleaned_body,
                max_tokens=budget,
                model=self.model,
            )

            # 6. Compute cryptographic SHA-256 content hash
            content_hash = hashlib.sha256(truncated_body.encode("utf-8")).hexdigest()

            # 7. Structural encapsulation
            safe_attr = "true" if is_safe else "false"
            if wrap_tags:
                encapsulated = (
                    f'<untrusted_supplier_data source="{source_id}" safe="{safe_attr}" hash="{content_hash}">\n'
                    f"{truncated_body}\n"
                    f"</untrusted_supplier_data>"
                )
            else:
                encapsulated = truncated_body

            span.set_attribute("injection.score", float(injection_score))
            span.set_attribute("is_safe", is_safe)
            span.set_attribute("is_truncated", is_truncated)
            span.set_attribute("token_count", token_count)

            payload = SanitizedPayload(
                sanitized_text=encapsulated,
                inner_text=truncated_body,
                raw_hash=raw_hash,
                content_hash=content_hash,
                injection_score=injection_score,
                is_safe=is_safe,
                token_count=token_count,
                is_truncated=is_truncated,
                source_id=source_id,
                audit_logged=False,
            )

            logger.info(
                "Quarantined text sanitized: source=%s safe=%s score=%.2f tokens=%d truncated=%s hash=%s",
                source_id,
                is_safe,
                injection_score,
                token_count,
                is_truncated,
                content_hash[:12],
            )

            if not is_safe and raise_on_injection:
                raise PromptInjectionDetectedError(
                    injection_score=injection_score,
                    payload=payload,
                )

            return payload

    async def sanitize_async(
        self,
        raw_text: str,
        source_id: str = "unknown",
        max_tokens: int | None = None,
        wrap_tags: bool = True,
        raise_on_injection: bool = False,
        record_audit: bool = True,
        strict_audit: bool = False,
        actor_id: str = "sys-quarantined-reader",
    ) -> SanitizedPayload:
        """Sanitize an untrusted text payload asynchronously and record forensic audit log."""
        payload = self.sanitize(
            raw_text=raw_text,
            source_id=source_id,
            max_tokens=max_tokens,
            wrap_tags=wrap_tags,
            raise_on_injection=raise_on_injection,
        )

        if not record_audit:
            return payload

        # Record immutable forensic audit log entry (BR-RULE-007)
        audit_logged = False
        try:
            await write_audit_log(
                entity_type="untrusted_supplier_data",
                entity_id=payload.content_hash,
                action="SANITIZE_AND_QUARANTINE",
                actor_id=actor_id,
                before_state={
                    "raw_hash": payload.raw_hash,
                    "source_id": source_id,
                    "raw_length": len(raw_text or ""),
                },
                after_state={
                    "content_hash": payload.content_hash,
                    "is_safe": payload.is_safe,
                    "injection_score": payload.injection_score,
                    "token_count": payload.token_count,
                    "is_truncated": payload.is_truncated,
                },
                trace_id=get_trace_id(),
            )
            audit_logged = True
        except Exception as exc:
            logger.warning(
                "Failed to write forensic audit log for quarantined text [hash=%s]: %s",
                payload.content_hash,
                exc,
            )
            if strict_audit:
                raise

        # Return updated payload with audit_logged flag
        return SanitizedPayload(
            sanitized_text=payload.sanitized_text,
            inner_text=payload.inner_text,
            raw_hash=payload.raw_hash,
            content_hash=payload.content_hash,
            injection_score=payload.injection_score,
            is_safe=payload.is_safe,
            token_count=payload.token_count,
            is_truncated=payload.is_truncated,
            source_id=payload.source_id,
            audit_logged=audit_logged,
        )

    def extract(
        self,
        documents: Sequence[str | dict[str, Any] | Any],
        max_tokens_per_doc: int | None = None,
    ) -> str:
        """Extract and quarantine evidence from a collection of documents/news/contracts.

        Conforms to CLAUDE.md:
        `evidence=quarantined_reader.extract(contracts + news_articles)`
        """
        if not documents:
            return ""

        sanitized_sections: list[str] = []
        for i, doc in enumerate(documents):
            if isinstance(doc, dict):
                content = str(doc.get("content") or doc.get("text") or doc.get("body") or "")
                source_id = str(
                    doc.get("source") or doc.get("source_id") or doc.get("id") or f"doc-{i + 1}"
                )
            else:
                content = str(doc)
                source_id = f"doc-{i + 1}"

            payload = self.sanitize(
                content,
                source_id=source_id,
                max_tokens=max_tokens_per_doc,
                wrap_tags=True,
            )
            sanitized_sections.append(payload.sanitized_text)

        return "\n\n".join(sanitized_sections)


# ------------------------------------------------------------------------------
# Module Singleton & Convenience Functions
# ------------------------------------------------------------------------------

quarantined_reader = QuarantinedReader()


def get_quarantined_reader() -> QuarantinedReader:
    """Return the global QuarantinedReader singleton instance."""
    return quarantined_reader


def sanitize(
    raw_text: str,
    source_id: str = "unknown",
    max_tokens: int | None = None,
    wrap_tags: bool = True,
    raise_on_injection: bool = False,
) -> SanitizedPayload:
    """Convenience functional wrapper for QuarantinedReader.sanitize()."""
    return quarantined_reader.sanitize(
        raw_text=raw_text,
        source_id=source_id,
        max_tokens=max_tokens,
        wrap_tags=wrap_tags,
        raise_on_injection=raise_on_injection,
    )
