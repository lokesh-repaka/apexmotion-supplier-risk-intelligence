"""LangGraph Detective Agent node implementations.

Provides specialized deterministic and LLM-assisted workflow nodes:
- triage_node: Deterministic signal classification, prompt quarantine, and fan-out routing (P9-2).
- research_node: Specialized intelligence gathering via News, SEC EDGAR, Geopolitical tools (P9-3).
- contract_node: Confidential contract clause extraction via vLLM with data sovereignty enforcement (P9-4).
- risk_node: Deterministic supply chain risk calculation and qualitative narrative synthesis (P9-5).
- recommendation_node: Procurement mitigation option generation and HITL spend tier gating (P9-6).
"""

from src.agents.nodes.contract_agent import (
    NODE_CONTRACT,
    ContractAgent,
    contract_node,
    get_contract_agent,
)
from src.agents.nodes.recommendation_agent import (
    NODE_RECOMMENDATION,
    RecommendationAgent,
    get_recommendation_agent,
    recommendation_node,
)
from src.agents.nodes.research_agent import (
    NODE_RESEARCH,
    ResearchAgent,
    get_research_agent,
    research_node,
)
from src.agents.nodes.risk_agent import (
    NODE_RISK,
    RiskAgent,
    get_risk_agent,
    risk_node,
)
from src.agents.nodes.triage_agent import (
    NODE_DISMISS,
    NODE_TRIAGE,
    TriageAgent,
    TriageResult,
    get_triage_agent,
    triage_node,
)

__all__ = [
    "ContractAgent",
    "NODE_CONTRACT",
    "NODE_DISMISS",
    "NODE_RECOMMENDATION",
    "NODE_RESEARCH",
    "NODE_RISK",
    "NODE_TRIAGE",
    "RecommendationAgent",
    "ResearchAgent",
    "RiskAgent",
    "TriageAgent",
    "TriageResult",
    "contract_node",
    "get_contract_agent",
    "get_recommendation_agent",
    "get_research_agent",
    "get_risk_agent",
    "get_triage_agent",
    "recommendation_node",
    "research_node",
    "risk_node",
    "triage_node",
]
