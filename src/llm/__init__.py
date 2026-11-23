"""LLM Gateway, Prompt Engineering & Guardrails package for ApexMotion platform.

Contains:
- LiteLLMGateway: Resilient LiteLLM client for Amazon Bedrock Claude 3.5 Sonnet / Haiku.
- Model routing, fallback, rate limiting, and exact Decimal token cost tracking.
- QuarantinedReader: Prompt injection defense, tag stripping, token budget enforcement,
  cryptographic hashing, and passive XML structural encapsulation.
- Pydantic Output Schemas: Strongly-typed response models for every LLM call (P8-3).
"""

from src.llm.gateway import (
    CostReport,
    LiteLLMGateway,
    LLMContextWindowExceededError,
    LLMGatewayError,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    TaskType,
    calculate_token_cost,
    get_litellm_gateway,
)
from src.llm.models import (
    Citation,
    CitationSourceType,
    ContractAnalysis,
    IncidentCaseDossier,
    IncidentCategory,
    MitigationScenario,
    MitigationStrategyType,
    RecommendationReport,
    ResearchAnalysis,
    RiskNarrative,
    StructuredOutputParsingError,
    parse_structured_llm_response,
)
from src.llm.quarantined_reader import (
    DEFAULT_MAX_TOKENS,
    PromptInjectionDetectedError,
    QuarantinedReader,
    SanitizedPayload,
    get_quarantined_reader,
    quarantined_reader,
    sanitize,
)

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "Citation",
    "CitationSourceType",
    "ContractAnalysis",
    "CostReport",
    "IncidentCaseDossier",
    "IncidentCategory",
    "LLMContextWindowExceededError",
    "LLMGatewayError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMServiceUnavailableError",
    "LLMTimeoutError",
    "LiteLLMGateway",
    "MitigationScenario",
    "MitigationStrategyType",
    "PromptInjectionDetectedError",
    "QuarantinedReader",
    "RecommendationReport",
    "ResearchAnalysis",
    "RiskNarrative",
    "SanitizedPayload",
    "StructuredOutputParsingError",
    "TaskType",
    "calculate_token_cost",
    "get_litellm_gateway",
    "get_quarantined_reader",
    "parse_structured_llm_response",
    "quarantined_reader",
    "sanitize",
]
