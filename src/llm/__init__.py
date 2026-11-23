"""LLM Gateway, Prompt Engineering & Guardrails package for ApexMotion platform.

Contains:
- LiteLLMGateway: Resilient LiteLLM client for Amazon Bedrock Claude 3.5 Sonnet / Haiku (P8-1).
- QuarantinedReader: Prompt injection defense, tag stripping, token budget enforcement,
  cryptographic hashing, and passive XML structural encapsulation (P8-2).
- Pydantic Output Schemas: Strongly-typed response models for every LLM call (P8-3).
- VLLMClient & ConfidentialContractRouter: vLLM confidential contract client ensuring
  EU-regulated contracts route strictly to self-hosted vLLM endpoint, never to Bedrock (P8-4).
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
from src.llm.vllm_client import (
    EU_EEA_JURISDICTIONS,
    ConfidentialContractRouter,
    ContractClassification,
    ContractMetadata,
    VLLMClient,
    VLLMClientError,
    VLLMConnectionError,
    VLLMContractExtractionError,
    VLLMDataSovereigntyViolationError,
    VLLMTimeoutError,
    get_contract_router,
    get_vllm_client,
)

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "Citation",
    "CitationSourceType",
    "ConfidentialContractRouter",
    "ContractAnalysis",
    "ContractClassification",
    "ContractMetadata",
    "CostReport",
    "EU_EEA_JURISDICTIONS",
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
    "VLLMClient",
    "VLLMClientError",
    "VLLMConnectionError",
    "VLLMContractExtractionError",
    "VLLMDataSovereigntyViolationError",
    "VLLMTimeoutError",
    "calculate_token_cost",
    "get_contract_router",
    "get_litellm_gateway",
    "get_quarantined_reader",
    "get_vllm_client",
    "parse_structured_llm_response",
    "quarantined_reader",
    "sanitize",
]
