"""Input Sanitizer Guardrail Component for ApexMotion Supplier Risk Intelligence Platform.

Module: src.guardrails.input_sanitizer
Implements:
- Layering Invariants (CLAUDE.md Sec 5.2, Sec 8.1, Sec 14): Sanitizes all untrusted external text
  (supplier contracts, news articles, SEC filings, supplier emails) before inclusion in any LLM prompt.
- XML Injection Defense: Strips HTML/XML tags, CDATA blocks, DOCTYPE / XXE declarations, comments,
  and tag-breakout attempts (</untrusted_supplier_data>, <system>, <instructions>, etc.).
- Markdown Injection Defense: Neutralizes executable URI schemes (javascript:, data:, vbscript:)
  in markdown links and images, and defuses adversarial markdown header manipulation.
- Unicode Bypass Defense: Normalizes fullwidth characters via NFKC, strips invisible zero-width
  spaces and joiners (\u200b, \u200c, \u200d, \ufeff), strips BiDi direction overrides (\u202e, etc.),
  and normalizes Cyrillic/Greek homoglyphs to defeat regex evasion.
- Prompt Injection Defense: Detects adversarial jailbreaks, directives, and instruction overrides,
  scores malicious potential, and redacts malicious directives.
- Clean Text Passthrough: Preserves benign multilingual text (German, French, Spanish, Japanese, etc.),
  currency symbols ($ € £ ¥), standard punctuation, and contract terminology with zero corruption.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.core.logging import get_logger

logger = get_logger("apexmotion.guardrails.input_sanitizer")

# ------------------------------------------------------------------------------
# Constants & Regular Expressions
# ------------------------------------------------------------------------------

# Non-printable ASCII control characters: null (0x00) through backspace (0x08),
# vertical tab (0x0B), form feed (0x0C), shift out (0x0E) through unit separator (0x1F), and DEL (0x7F).
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Invisible Unicode characters used to break keyword tokens:
# \u200B (Zero-width space), \u200C (ZWNJ), \u200D (ZWJ), \u200E (LRM), \u200F (RLM),
# \uFEFF (BOM / ZWNBSP), \u2060 (Word joiner), \u00AD (Soft hyphen),
# \u2061-\u2064 (Invisible math operators)
INVISIBLE_UNICODE_REGEX = re.compile(r"[\u200B-\u200F\uFEFF\u2060\u00AD\u2061-\u2064]")

# Bidirectional text override characters:
# \u202A-\u202E (LRE, RLE, PDF, LRO, RLO), \u2066-\u2069 (LRI, RLI, FSI, PDI)
BIDI_OVERRIDE_REGEX = re.compile(r"[\u202A-\u202E\u2066-\u2069]")

# Cyrillic and Greek homoglyphs commonly used to evade ASCII prompt injection regexes
HOMOGLYPH_TRANSLATION_TABLE = str.maketrans(
    {
        # Cyrillic lowercase
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "ԁ": "d",
        "ԛ": "q",
        "ԝ": "w",
        # Cyrillic uppercase
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "І": "I",
        "Ј": "J",
        "Ѕ": "S",
        # Greek lowercase & uppercase
        "ο": "o",
        "ν": "v",
        "ρ": "p",
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
    }
)

# HTML/XML comments hiding payloads: <!-- ... -->
HTML_COMMENTS_REGEX = re.compile(r"<!--[\s\S]*?-->")

# CDATA sections: <![CDATA[ ... ]]>
CDATA_REGEX = re.compile(r"<!\[CDATA\[([\s\S]*?)\]\]>", re.IGNORECASE)

# Dangerous script, style, XML declarations, and DOCTYPE / XXE blocks
SCRIPT_STYLE_BLOCKS_REGEX = re.compile(
    r"<(script|style|xml|\?xml|!DOCTYPE)[^>]*>[\s\S]*?(</\1>|$|>)",
    re.IGNORECASE,
)

# Delimiter breakout tag defense (strips attempts to close or re-open sandbox tags)
DELIMITER_BREAKOUT_REGEX = re.compile(
    r"<\/?\s*(untrusted_supplier_data|untrusted_signal|system|instructions|prompt|admin)[^>]*>",
    re.IGNORECASE,
)

# General HTML/XML tags
HTML_TAGS_REGEX = re.compile(r"<[^>]+>")

# Markdown dangerous URI schemes in links: [click](javascript:alert(1)) or [link](data:...)
MARKDOWN_DANGEROUS_LINKS_REGEX = re.compile(
    r"(?<!\!)\[([^\]]*)\]\(\s*(javascript|data|vbscript):[^\)]*\)",
    re.IGNORECASE,
)

# Markdown dangerous image links: ![img](javascript:...) or ![img](data:...)
MARKDOWN_DANGEROUS_IMAGES_REGEX = re.compile(
    r"!\[([^\]]*)\]\(\s*(javascript|data|vbscript):[^\)]*\)",
    re.IGNORECASE,
)

# High-risk adversarial prompt injection directives (LLD Sec 5.2 & CLAUDE.md Sec 8.1)
INJECTION_DIRECTIVES_REGEX = re.compile(
    r"("
    r"ignore\s+(all\s+)?prior\s+instructions|"
    r"disregard\s+(all\s+)?(previous|prior)\s+(prompts?|instructions?)|"
    r"forget\s+(all\s+)?(previous|prior)\s+(prompts?|instructions?)|"
    r"you\s+are\s+now\s+(a\s+|an\s+)?[a-z0-9_-]+|"
    r"system\s+override|"
    r"bypass\s+all\s+rules|"
    r"drop\s+table|"
    r"reveal\s+(all\s+)?system\s+prompts?|"
    r"output\s+(all\s+)?system\s+prompts?|"
    r"output\s+the\s+initial\s+prompt|"
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
# Data Models & Exceptions
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SanitizationResult:
    """Immutable result of input sanitization holding cleaned text and detection metadata."""

    cleaned_text: str
    raw_hash: str
    content_hash: str
    injection_score: float
    is_safe: bool
    has_xml_breakout: bool
    has_markdown_exploit: bool
    has_unicode_evasion: bool
    removed_tags_count: int

    def __str__(self) -> str:
        """Return the cleaned text representation."""
        return self.cleaned_text


class PromptInjectionDetectedError(Exception):
    """Raised in strict mode when untrusted text contains prompt injection directives (RFC 7807)."""

    def __init__(
        self,
        message: str = "Input payload contained blacklisted instruction sequences. Text has been quarantined.",
        injection_score: float = 0.0,
        result: SanitizationResult | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = 422
        self.error_code = "SEC_422_INJECTION"
        self.injection_score = injection_score
        self.result = result
        self.payload = payload


# ------------------------------------------------------------------------------
# Core InputSanitizer Service
# ------------------------------------------------------------------------------


class InputSanitizer:
    """Enterprise-grade input sanitization engine protecting LLMs from prompt injection attacks."""

    def __init__(self, injection_threshold: float = 0.40) -> None:
        self.injection_threshold = injection_threshold

    def sanitize(
        self,
        raw_text: str,
        raise_on_injection: bool = False,
    ) -> SanitizationResult:
        """Sanitize an untrusted text string across XML, Markdown, Unicode, and Injection vectors."""
        raw_hash = hashlib.sha256((raw_text or "").encode("utf-8")).hexdigest()

        if not raw_text or not raw_text.strip():
            empty_hash = hashlib.sha256(b"").hexdigest()
            return SanitizationResult(
                cleaned_text="",
                raw_hash=raw_hash,
                content_hash=empty_hash,
                injection_score=0.0,
                is_safe=True,
                has_xml_breakout=False,
                has_markdown_exploit=False,
                has_unicode_evasion=False,
                removed_tags_count=0,
            )

        # ----------------------------------------------------------------------
        # 1. Unicode Normalization & Bypass Defense
        # ----------------------------------------------------------------------
        has_unicode_evasion = False

        # Detect and strip invisible zero-width characters and joiners
        if INVISIBLE_UNICODE_REGEX.search(raw_text):
            has_unicode_evasion = True
        stripped_invisible = INVISIBLE_UNICODE_REGEX.sub("", raw_text)

        # Detect and strip bidirectional override characters
        if BIDI_OVERRIDE_REGEX.search(stripped_invisible):
            has_unicode_evasion = True
        stripped_bidi = BIDI_OVERRIDE_REGEX.sub("", stripped_invisible)

        # Strip non-printable ASCII control characters
        stripped_control = CONTROL_CHARS_REGEX.sub("", stripped_bidi)

        # Normalize Unicode via NFKC (collapses full-width characters, ligatures, etc.)
        normalized_unicode = unicodedata.normalize("NFKC", stripped_control)

        # ----------------------------------------------------------------------
        # 2. XML / HTML Injection Defense
        # ----------------------------------------------------------------------
        has_xml_breakout = False
        removed_tags_count = 0

        # Unwrap CDATA sections while keeping their inner text
        unwrapped_cdata = CDATA_REGEX.sub(r"\1", normalized_unicode)

        # Strip HTML/XML comments entirely
        no_comments = HTML_COMMENTS_REGEX.sub("", unwrapped_cdata)

        # Decode HTML entities (&lt;, &gt;, &quot;, &#x...;)
        decoded = html.unescape(no_comments)

        # Strip script, style, XML declaration, and DOCTYPE blocks
        no_scripts = SCRIPT_STYLE_BLOCKS_REGEX.sub("", decoded)

        # Detect delimiter breakout tags (<untrusted_supplier_data>, <system>, etc.)
        if DELIMITER_BREAKOUT_REGEX.search(no_scripts):
            has_xml_breakout = True
        neutralized_delimiters = DELIMITER_BREAKOUT_REGEX.sub("", no_scripts)

        # Count and strip any remaining general HTML/XML tags
        found_tags = HTML_TAGS_REGEX.findall(neutralized_delimiters)
        removed_tags_count += len(found_tags)
        no_html = HTML_TAGS_REGEX.sub("", neutralized_delimiters)

        # ----------------------------------------------------------------------
        # 3. Markdown Injection Defense
        # ----------------------------------------------------------------------
        has_markdown_exploit = False

        # Neutralize dangerous executable URI schemes in markdown images first
        if MARKDOWN_DANGEROUS_IMAGES_REGEX.search(no_html):
            has_markdown_exploit = True
        neutralized_images = MARKDOWN_DANGEROUS_IMAGES_REGEX.sub(
            r"[BLOCKED_IMAGE: \1]",
            no_html,
        )

        # Neutralize dangerous executable URI schemes in markdown links
        if MARKDOWN_DANGEROUS_LINKS_REGEX.search(neutralized_images):
            has_markdown_exploit = True
        neutralized_markdown = MARKDOWN_DANGEROUS_LINKS_REGEX.sub(
            r"[\1] [BLOCKED_URI_SCHEME]",
            neutralized_images,
        )

        # ----------------------------------------------------------------------
        # 4. Homoglyph Normalization for Prompt Injection Detection
        # ----------------------------------------------------------------------
        # Translate Cyrillic and Greek homoglyphs to Latin to defeat regex evasion
        homoglyph_normalized = neutralized_markdown.translate(HOMOGLYPH_TRANSLATION_TABLE)
        if homoglyph_normalized != neutralized_markdown:
            # Check if homoglyph substitution was used in conjunction with potential injection
            if INJECTION_DIRECTIVES_REGEX.search(homoglyph_normalized):
                has_unicode_evasion = True

        # Check for adversarial injection signatures on the homoglyph-normalized text
        matches = INJECTION_DIRECTIVES_REGEX.findall(homoglyph_normalized)
        injection_score = min(1.0, len(matches) * 0.45) if matches else 0.0
        is_safe = injection_score < self.injection_threshold

        # Redact malicious directives from the sanitized text using the matching positions
        redacted = INJECTION_DIRECTIVES_REGEX.sub(
            "[REDACTED_ADVERSARIAL_DIRECTIVE]",
            homoglyph_normalized if has_unicode_evasion else neutralized_markdown,
        )

        # Clean internal whitespace while preserving paragraph line breaks
        lines = [line.strip() for line in redacted.splitlines()]
        cleaned_body = "\n".join(line for line in lines if line)

        # Compute cryptographic content hash
        content_hash = hashlib.sha256(cleaned_body.encode("utf-8")).hexdigest()

        result = SanitizationResult(
            cleaned_text=cleaned_body,
            raw_hash=raw_hash,
            content_hash=content_hash,
            injection_score=injection_score,
            is_safe=is_safe,
            has_xml_breakout=has_xml_breakout,
            has_markdown_exploit=has_markdown_exploit,
            has_unicode_evasion=has_unicode_evasion,
            removed_tags_count=removed_tags_count,
        )

        if not is_safe and raise_on_injection:
            raise PromptInjectionDetectedError(
                injection_score=injection_score,
                result=result,
            )

        return result


# ------------------------------------------------------------------------------
# Module Singleton & Convenience Functional Interface
# ------------------------------------------------------------------------------

input_sanitizer = InputSanitizer()


def get_input_sanitizer() -> InputSanitizer:
    """Return the global InputSanitizer singleton instance."""
    return input_sanitizer


def sanitize_input(
    raw_text: str,
    raise_on_injection: bool = False,
) -> SanitizationResult:
    """Convenience functional wrapper for InputSanitizer.sanitize()."""
    return input_sanitizer.sanitize(raw_text=raw_text, raise_on_injection=raise_on_injection)
