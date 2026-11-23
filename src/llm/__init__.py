"""LLM Gateway, Prompt Engineering & Guardrails package for ApexMotion platform.

Contains:
- LiteLLMGateway: Resilient LiteLLM client for Amazon Bedrock Claude 3.5 Sonnet / Haiku.
- Model routing, fallback, rate limiting, and exact Decimal token cost tracking.
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

__all__ = [
    "CostReport",
    "LLMContextWindowExceededError",
    "LLMGatewayError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMServiceUnavailableError",
    "LLMTimeoutError",
    "LiteLLMGateway",
    "TaskType",
    "calculate_token_cost",
    "get_litellm_gateway",
]
