"""LangGraph Detective Agent node implementations.

Provides specialized deterministic and LLM-assisted workflow nodes:
- triage_node: Deterministic signal classification, prompt quarantine, and fan-out routing (P9-2).
- research_node: Specialized intelligence gathering via News, SEC EDGAR, Geopolitical tools (P9-3).
"""

from src.agents.nodes.research_agent import (
    NODE_RESEARCH,
    ResearchAgent,
    get_research_agent,
    research_node,
)
from src.agents.nodes.triage_agent import (
    NODE_CONTRACT,
    NODE_DISMISS,
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
    "ResearchAgent",
    "TriageAgent",
    "TriageResult",
    "get_research_agent",
    "get_triage_agent",
    "research_node",
    "triage_node",
]
