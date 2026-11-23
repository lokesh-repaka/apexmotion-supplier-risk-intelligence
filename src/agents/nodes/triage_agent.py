"""Deterministic Triage Agent Node & Signal Classification (P9-2).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Zero LLM math, zero LLM classification — 100% deterministic Python rule and keyword engine.
  * Deterministically categorizes disruption signals into:
    - news (cleanroom fire, fab explosion, contamination, equipment failure, disasters)
    - financial (insolvency, bankruptcy, Chapter 11, liquidity crisis, debt default, downgrade)
    - logistics (port congestion, customs hold, freight/vessel delays, container demurrage)
    - geopolitical (export controls, tariffs, trade sanctions, embargoes, entity list)
  * Assigns deterministic confidence scores and extracts matched indicators.
- Untrusted Input Quarantine & Prompt Injection Defense (CLAUDE.md Sec 8.1 & LLD Sec 5.2):
  * All raw untrusted signals pass through QuarantinedReader before state propagation.
  * Strips XML breakout tags, script tags, non-printable control characters, and redacts adversarial prompts.
- Deterministic Routing Topology (LLD Sec 4.2):
  * News / Logistics / Geopolitical -> Research Node
  * Financial -> Contract Node
  * Composite (both financial and operational disruption) -> Parallel Fan-out [Research, Contract]
  * Benign / Verified Zero Impact -> Dismiss Node
"""

import re
import threading
from dataclasses import dataclass
from typing import Any

from src.agents.state import (
    SignalType,
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.logging import get_logger
from src.llm.quarantined_reader import get_quarantined_reader

logger = get_logger("apexmotion.agents.triage")

# ------------------------------------------------------------------------------
# Node Identifiers (decoupled from graph.py to prevent circular imports)
# ------------------------------------------------------------------------------

NODE_TRIAGE = "triage"
NODE_RESEARCH = "research"
NODE_CONTRACT = "contract"
NODE_DISMISS = "dismiss"


# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class TriageResult:
    """Immutable outcome of deterministic signal triage classification."""

    signal_type: SignalType
    confidence: float
    detected_keywords: list[str]
    quarantined_text: str
    is_zero_impact: bool
    target_nodes: list[str]
    summary: str


# ------------------------------------------------------------------------------
# Classification Taxonomies & Regex Patterns
# ------------------------------------------------------------------------------

ZERO_IMPACT_PATTERNS = [
    re.compile(r"\bzero[\s\-_]impact\b", re.IGNORECASE),
    re.compile(r"\bzero[\s\-_]downtime\b", re.IGNORECASE),
    re.compile(r"\bcleared\s+with\s+zero\b", re.IGNORECASE),
    re.compile(r"\broutine\s+(annual\s+)?maintenance\b", re.IGNORECASE),
    re.compile(r"\bahead\s+of\s+schedule\b", re.IGNORECASE),
    re.compile(r"\bminor\s+inspection\s+pause\s+cleared\b", re.IGNORECASE),
    re.compile(r"\bno\s+(operational\s+|production\s+)?impact\b", re.IGNORECASE),
    re.compile(r"\bnegligible\s+impact\b", re.IGNORECASE),
    re.compile(r"\bnormal\s+operations\b", re.IGNORECASE),
    re.compile(r"\bfalse\s+alarm\b", re.IGNORECASE),
]

FINANCIAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("bankruptcy", re.compile(r"\bbankrupt(cy)?\b", re.IGNORECASE)),
    ("chapter 11", re.compile(r"\bchapter\s+11\b", re.IGNORECASE)),
    ("insolvency", re.compile(r"\binsolven(cy|t)\b", re.IGNORECASE)),
    ("liquidity", re.compile(r"\bliquidity\b", re.IGNORECASE)),
    ("debt default", re.compile(r"\bdebt\s+defaults?\b", re.IGNORECASE)),
    ("covenant default", re.compile(r"\bcovenant\s+defaults?\b", re.IGNORECASE)),
    ("default", re.compile(r"\bdefaults?\b", re.IGNORECASE)),
    ("credit downgrade", re.compile(r"\bcredit\s+downgrades?\b", re.IGNORECASE)),
    ("downgrade", re.compile(r"\bdowngrades?\b", re.IGNORECASE)),
    ("restructuring", re.compile(r"\brestructur(ing|ed)\b", re.IGNORECASE)),
    ("distressed", re.compile(r"\bdistressed\b", re.IGNORECASE)),
    ("receivership", re.compile(r"\breceivership\b", re.IGNORECASE)),
    ("cash flow", re.compile(r"\bcash[\s\-_]flow\b", re.IGNORECASE)),
]

LOGISTICS_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("port congestion", re.compile(r"\bport\s+congestion\b", re.IGNORECASE)),
    ("congestion", re.compile(r"\bcongest(ion|ed)\b", re.IGNORECASE)),
    ("customs clearance", re.compile(r"\bcustoms\s+clearance\b", re.IGNORECASE)),
    ("customs", re.compile(r"\bcustoms\b", re.IGNORECASE)),
    ("shipping delay", re.compile(r"\bshipping\s+delays?\b", re.IGNORECASE)),
    ("shipping", re.compile(r"\bshipping\b", re.IGNORECASE)),
    ("transit delay", re.compile(r"\btransit\s+delays?\b", re.IGNORECASE)),
    ("freight", re.compile(r"\bfreight\b", re.IGNORECASE)),
    ("container", re.compile(r"\bcontainers?\b", re.IGNORECASE)),
    ("vessel", re.compile(r"\bvessels?\b", re.IGNORECASE)),
    ("carrier", re.compile(r"\bcarriers?\b", re.IGNORECASE)),
    ("demurrage", re.compile(r"\bdemurrage\b", re.IGNORECASE)),
    ("dock strike", re.compile(r"\bdock\s+strikes?\b", re.IGNORECASE)),
    ("canal", re.compile(r"\bcanal\b", re.IGNORECASE)),
]

GEOPOLITICAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("export control", re.compile(r"\bexport\s+controls?\b", re.IGNORECASE)),
    ("tariff", re.compile(r"\btariffs?\b", re.IGNORECASE)),
    ("sanction", re.compile(r"\bsanctions?\b", re.IGNORECASE)),
    ("trade war", re.compile(r"\btrade\s+wars?\b", re.IGNORECASE)),
    ("embargo", re.compile(r"\bembargo(es)?\b", re.IGNORECASE)),
    ("entity list", re.compile(r"\bentity\s+list\b", re.IGNORECASE)),
    ("trade dispute", re.compile(r"\btrade\s+disputes?\b", re.IGNORECASE)),
    ("nationalization", re.compile(r"\bnationaliz(ation|ed)\b", re.IGNORECASE)),
    ("border closure", re.compile(r"\bborder\s+closures?\b", re.IGNORECASE)),
    ("civil unrest", re.compile(r"\bcivil\s+unrest\b", re.IGNORECASE)),
    ("geopolitical", re.compile(r"\bgeopolitical\b", re.IGNORECASE)),
]

NEWS_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("fire", re.compile(r"\bfires?\b", re.IGNORECASE)),
    ("cleanroom", re.compile(r"\bcleanrooms?\b", re.IGNORECASE)),
    ("contamination", re.compile(r"\bcontaminat(ion|ed)\b", re.IGNORECASE)),
    ("fab", re.compile(r"\bfabs?\b", re.IGNORECASE)),
    ("explosion", re.compile(r"\bexplosions?\b", re.IGNORECASE)),
    ("earthquake", re.compile(r"\bearthquakes?\b", re.IGNORECASE)),
    ("flood", re.compile(r"\bfloods?\b", re.IGNORECASE)),
    ("typhoon", re.compile(r"\btyphoons?\b", re.IGNORECASE)),
    ("hurricane", re.compile(r"\bhurricanes?\b", re.IGNORECASE)),
    ("power outage", re.compile(r"\bpower\s+outages?\b", re.IGNORECASE)),
    ("blackout", re.compile(r"\bblackouts?\b", re.IGNORECASE)),
    ("halted", re.compile(r"\bhalt(ed|ing)?\b", re.IGNORECASE)),
    ("equipment damage", re.compile(r"\bequipment\s+damag(ed|e)\b", re.IGNORECASE)),
    ("chemical spill", re.compile(r"\bchemical\s+spills?\b", re.IGNORECASE)),
    ("cyberattack", re.compile(r"\bcyber[\s\-_]?attacks?\b", re.IGNORECASE)),
    ("ransomware", re.compile(r"\bransomware\b", re.IGNORECASE)),
]


# ------------------------------------------------------------------------------
# Triage Agent Implementation
# ------------------------------------------------------------------------------


class TriageAgent:
    """Deterministic classifier evaluating disruption signals and quarantine sanitization."""

    def __init__(self) -> None:
        self.reader = get_quarantined_reader()

    def classify(
        self,
        signal_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> TriageResult:
        """Classify untrusted text deterministically into signal taxonomy and target nodes."""
        meta = metadata or {}
        source_id = meta.get("supplier_id") or meta.get("source_id") or "untrusted_signal"

        # 1. Sanitize and quarantine untrusted payload
        sanitized = self.reader.sanitize(
            raw_text=signal_text,
            source_id=source_id,
            wrap_tags=True,
        )
        quarantined_text = sanitized.sanitized_text

        # 2. Check for explicit zero impact in metadata
        if meta.get("zero_impact") is True or meta.get("is_zero_impact") is True:
            logger.info("Triage: Zero blast radius confirmed via metadata flag.")
            return TriageResult(
                signal_type=SignalType.NEWS,
                confidence=0.95,
                detected_keywords=[],
                quarantined_text=quarantined_text,
                is_zero_impact=True,
                target_nodes=[NODE_DISMISS],
                summary="Zero operational blast radius confirmed via metadata; routed to dismiss.",
            )

        # 3. Check for empty or blank payload
        if not signal_text or not signal_text.strip():
            logger.info("Triage: Empty signal text; defaulting to news research baseline.")
            return TriageResult(
                signal_type=SignalType.NEWS,
                confidence=0.50,
                detected_keywords=[],
                quarantined_text=quarantined_text,
                is_zero_impact=False,
                target_nodes=[NODE_RESEARCH],
                summary="Empty signal payload; defaulted to news research baseline.",
            )

        # 4. Check for benign/zero-impact keywords
        for pat in ZERO_IMPACT_PATTERNS:
            if pat.search(signal_text):
                logger.info("Triage: Detected zero-impact pattern in signal text.")
                return TriageResult(
                    signal_type=SignalType.NEWS,
                    confidence=0.95,
                    detected_keywords=[],
                    quarantined_text=quarantined_text,
                    is_zero_impact=True,
                    target_nodes=[NODE_DISMISS],
                    summary="Zero operational or financial impact detected in signal text; dismissed.",
                )

        # 5. Extract category keywords
        matches_by_type: dict[SignalType, list[str]] = {
            SignalType.FINANCIAL: [],
            SignalType.LOGISTICS: [],
            SignalType.GEOPOLITICAL: [],
            SignalType.NEWS: [],
        }
        detected_keywords: list[str] = []

        for kw, pat in FINANCIAL_RULES:
            if pat.search(signal_text):
                matches_by_type[SignalType.FINANCIAL].append(kw)
                if kw not in detected_keywords:
                    detected_keywords.append(kw)

        for kw, pat in LOGISTICS_RULES:
            if pat.search(signal_text):
                matches_by_type[SignalType.LOGISTICS].append(kw)
                if kw not in detected_keywords:
                    detected_keywords.append(kw)

        for kw, pat in GEOPOLITICAL_RULES:
            if pat.search(signal_text):
                matches_by_type[SignalType.GEOPOLITICAL].append(kw)
                if kw not in detected_keywords:
                    detected_keywords.append(kw)

        for kw, pat in NEWS_RULES:
            if pat.search(signal_text):
                matches_by_type[SignalType.NEWS].append(kw)
                if kw not in detected_keywords:
                    detected_keywords.append(kw)

        # 6. Fallback if no category keywords detected
        if not detected_keywords:
            logger.info(
                "Triage: No known taxonomy keywords matched; falling back to news research."
            )
            return TriageResult(
                signal_type=SignalType.NEWS,
                confidence=0.50,
                detected_keywords=[],
                quarantined_text=quarantined_text,
                is_zero_impact=False,
                target_nodes=[NODE_RESEARCH],
                summary="Unrecognized signal payload; defaulted to news research.",
            )

        # 7. Determine destination nodes (supports parallel fan-out)
        has_financial = len(matches_by_type[SignalType.FINANCIAL]) > 0
        has_operational = (
            len(matches_by_type[SignalType.NEWS]) > 0
            or len(matches_by_type[SignalType.LOGISTICS]) > 0
            or len(matches_by_type[SignalType.GEOPOLITICAL]) > 0
        )

        target_nodes: list[str] = []
        if has_operational:
            target_nodes.append(NODE_RESEARCH)
        if has_financial:
            target_nodes.append(NODE_CONTRACT)

        # 8. Select primary category by match count with deterministic tie-breaking
        category_priority = [
            SignalType.NEWS,
            SignalType.FINANCIAL,
            SignalType.LOGISTICS,
            SignalType.GEOPOLITICAL,
        ]
        best_type = max(
            category_priority,
            key=lambda st: len(matches_by_type[st]),
        )

        # 9. Compute deterministic confidence score
        hit_count = len(matches_by_type[best_type])
        if hit_count == 1:
            confidence = 0.82
        elif hit_count == 2:
            confidence = 0.88
        else:
            confidence = min(0.98, 0.88 + (hit_count - 2) * 0.03)

        summary = (
            f"Deterministic triage identified {best_type.value} disruption signal "
            f"with {confidence:.2f} confidence based on indicators: {', '.join(matches_by_type[best_type])}."
        )

        logger.info(
            "Triage result: type=%s confidence=%.2f targets=%s keywords=%s",
            best_type.value,
            confidence,
            target_nodes,
            detected_keywords,
        )

        return TriageResult(
            signal_type=best_type,
            confidence=confidence,
            detected_keywords=detected_keywords,
            quarantined_text=quarantined_text,
            is_zero_impact=False,
            target_nodes=target_nodes,
            summary=summary,
        )


# ------------------------------------------------------------------------------
# Thread-safe Singleton Instance
# ------------------------------------------------------------------------------

_triage_agent_instance: TriageAgent | None = None
_triage_agent_lock = threading.Lock()


def get_triage_agent() -> TriageAgent:
    """Return the thread-safe singleton instance of TriageAgent."""
    global _triage_agent_instance
    if _triage_agent_instance is None:
        with _triage_agent_lock:
            if _triage_agent_instance is None:
                _triage_agent_instance = TriageAgent()
    return _triage_agent_instance


# ------------------------------------------------------------------------------
# LangGraph Node Entrypoint
# ------------------------------------------------------------------------------


def triage_node(state: SupplierRiskState) -> dict[str, Any]:
    """LangGraph node: Classify signal, quarantine untrusted input, and establish route."""
    raw_signal = state.get("raw_signal") or ""
    metadata = dict(state.get("metadata") or {})
    supplier_id = state.get("supplier_id") or "unknown_supplier"

    if "supplier_id" not in metadata:
        metadata["supplier_id"] = supplier_id

    agent = get_triage_agent()
    result = agent.classify(raw_signal, metadata=metadata)

    is_zero = result.is_zero_impact
    status = WorkflowStatus.DISMISSED if is_zero else WorkflowStatus.TRIAGED

    metadata["is_zero_impact"] = is_zero
    metadata["target_nodes"] = result.target_nodes
    metadata["triage_confidence"] = result.confidence
    metadata["detected_keywords"] = result.detected_keywords

    sig_type_str = (
        result.signal_type.value
        if isinstance(result.signal_type, SignalType)
        else str(result.signal_type)
    )

    audit_event = {
        "action": "SIGNAL_TRIAGED",
        "signal_type": sig_type_str,
        "confidence": result.confidence,
        "target_nodes": result.target_nodes,
        "is_zero_impact": is_zero,
        "status": status.value if isinstance(status, WorkflowStatus) else str(status),
    }

    return {
        "current_node": NODE_TRIAGE,
        "execution_path": [NODE_TRIAGE],
        "workflow_status": status,
        "signal_type": result.signal_type,
        "quarantined_signal": result.quarantined_text,
        "metadata": metadata,
        "audit_events": [audit_event],
    }
