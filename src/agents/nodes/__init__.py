"""LangGraph Detective Agent node implementations.

Provides specialized deterministic and LLM-assisted workflow nodes:
- triage_node: Deterministic signal classification, prompt quarantine, and fan-out routing (P9-2).
"""

from src.agents.nodes.triage_agent import (
    NODE_CONTRACT,
    NODE_DISMISS,
    NODE_RESEARCH,
    NODE_TRIAGE,
    TriageAgent,
    TriageResult,
    get_triage_agent,
    triage_node,
)

__all__ = [
    "NODE_CONTRACT",
    "NODE_DISMISS",
    "NODE_RESEARCH",
    "NODE_TRIAGE",
    "TriageAgent",
    "TriageResult",
    "get_triage_agent",
    "triage_node",
]
