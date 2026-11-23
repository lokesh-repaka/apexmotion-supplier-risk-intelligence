"""LiteLLM Gateway client for ApexMotion platform (P8-1).

Enforces:
- Dynamic model routing:
  * Synthesis & deep reasoning (TaskType.SYNTHESIS) -> Amazon Bedrock Claude 3.5 Sonnet
  * Triage & entity extraction (TaskType.TRIAGE / EXTRACTION) -> Amazon Bedrock Claude 3.5 Haiku
- Automated resilient fallback:
  * Primary model failure (429 RateLimit, 503 Outage, 504 Timeout) triggers secondary model fallback
- Token usage metering & financial cost tracking:
  * Exact Decimal monetary tracking per BR-RULE-001 (zero floating-point drift)
- Offline mock mode (USE_MOCK_LLM=true):
  * Zero live cloud/external network calls in unit tests (CLAUDE.md Section 14)
- Distributed observability:
  * Propagates trace_id across all calls
"""

import asyncio
import hashlib
import json
import threading
import time
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    ContextWindowExceededError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from pydantic import BaseModel, Field

from src.api.exceptions import AppException
from src.core.config import Settings, get_settings
from src.core.logging import get_logger, get_trace_id

logger = get_logger("apexmotion.llm.gateway")

# ------------------------------------------------------------------------------
# Model Cost Rates per 1M Tokens (USD)
# ------------------------------------------------------------------------------

# Pricing per 1,000,000 tokens (Anthropic Bedrock official rates)
# Claude 3.5 Sonnet: $3.00 input, $15.00 output
# Claude 3.5 Haiku: $0.80 input, $4.00 output
MODEL_PRICING_PER_1M = {
    "claude-3-5-sonnet": {
        "input": Decimal("3.00"),
        "output": Decimal("15.00"),
    },
    "claude-3-5-haiku": {
        "input": Decimal("0.80"),
        "output": Decimal("4.00"),
    },
}

DEFAULT_INPUT_RATE_PER_1M = Decimal("3.00")
DEFAULT_OUTPUT_RATE_PER_1M = Decimal("15.00")
ONE_MILLION = Decimal("1000000")
PRECISION_COST = Decimal("0.000001")


# ------------------------------------------------------------------------------
# Enums & Domain Models
# ------------------------------------------------------------------------------


class TaskType(StrEnum):
    """Task complexity classification determining model routing."""

    SYNTHESIS = "synthesis"  # Complex synthesis, narrative reasoning -> Sonnet
    EXTRACTION = "extraction"  # Contract clauses, supplier entities -> Haiku
    TRIAGE = "triage"  # Signal classification, rapid severity check -> Haiku
    GENERAL = "general"  # Default routing


class LLMResponse(BaseModel):
    """Structured response payload from LiteLLM gateway."""

    content: str = Field(description="Generated model text completion")
    model: str = Field(description="Actual model invoked for generation")
    prompt_tokens: int = Field(default=0, description="Input token count")
    completion_tokens: int = Field(default=0, description="Generated token count")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    cost_usd: Decimal = Field(
        default=Decimal("0.000000"),
        description="Exact financial cost in USD",
    )
    latency_ms: float = Field(default=0.0, description="Latency in milliseconds")
    is_fallback: bool = Field(
        default=False,
        description="Whether secondary fallback model was used",
    )
    is_cached: bool = Field(
        default=False,
        description="Whether result was served from cache",
    )
    trace_id: str | None = Field(default=None, description="Distributed trace identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider/call metadata",
    )


class CostReport(BaseModel):
    """Aggregated token usage and financial expenditure ledger."""

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0.000000")
    call_count: int = 0
    fallback_count: int = 0
    cache_hit_count: int = 0
    model_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class LLMGatewayError(AppException):
    """Base exception for model gateway failures."""

    def __init__(
        self,
        message: str,
        code: str = "LLM_GATEWAY_ERROR",
        status_code: int = 500,
        details: Any = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class LLMRateLimitError(LLMGatewayError):
    """Raised when all provider rate limits and throttles are exceeded (HTTP 429)."""

    def __init__(self, message: str = "LiteLLM rate limit exceeded", details: Any = None) -> None:
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=429,
            details=details,
        )


class LLMTimeoutError(LLMGatewayError):
    """Raised when LLM call exceeds execution deadline (HTTP 504)."""

    def __init__(self, message: str = "LLM gateway timeout exceeded", details: Any = None) -> None:
        super().__init__(
            code="GATEWAY_TIMEOUT",
            message=message,
            status_code=504,
            details=details,
        )


class LLMServiceUnavailableError(LLMGatewayError):
    """Raised when upstream LLM providers are unavailable (HTTP 503)."""

    def __init__(
        self,
        message: str = "LLM service temporarily unavailable",
        details: Any = None,
    ) -> None:
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )


class LLMContextWindowExceededError(LLMGatewayError):
    """Raised when prompt exceeds model context length (HTTP 400)."""

    def __init__(
        self,
        message: str = "Prompt exceeds model context window",
        details: Any = None,
    ) -> None:
        super().__init__(
            code="CONTEXT_WINDOW_EXCEEDED",
            message=message,
            status_code=400,
            details=details,
        )


# ------------------------------------------------------------------------------
# Cost Calculation Engine (BR-RULE-001)
# ------------------------------------------------------------------------------


def calculate_token_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Calculate exact USD token cost adhering strictly to Decimal precision."""
    model_lower = model.lower()
    pricing = None
    for key, rates in MODEL_PRICING_PER_1M.items():
        if key in model_lower:
            pricing = rates
            break

    input_rate = pricing["input"] if pricing else DEFAULT_INPUT_RATE_PER_1M
    output_rate = pricing["output"] if pricing else DEFAULT_OUTPUT_RATE_PER_1M

    cost_in = (Decimal(prompt_tokens) * input_rate) / ONE_MILLION
    cost_out = (Decimal(completion_tokens) * output_rate) / ONE_MILLION

    total = cost_in + cost_out
    return total.quantize(PRECISION_COST, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------------------
# Gateway Implementation
# ------------------------------------------------------------------------------


class LiteLLMGateway:
    """Central model routing, resilient execution, and cost metering client."""

    def __init__(
        self,
        settings: Settings | None = None,
        use_mock: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.use_mock = use_mock if use_mock is not None else self.settings.USE_MOCK_LLM
        self.primary_model = self.settings.BEDROCK_SYNTHESIS_MODEL
        self.fallback_model = self.settings.BEDROCK_EXTRACTION_MODEL
        self.base_url = self.settings.LITELLM_BASE_URL

        # Thread-safe cost & usage metering
        self._lock = threading.Lock()
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost_usd = Decimal("0.000000")
        self._call_count = 0
        self._fallback_count = 0
        self._cache_hit_count = 0
        self._model_breakdown: dict[str, dict[str, Any]] = {}

        # In-memory prompt cache
        self._cache: dict[str, LLMResponse] = {}

    def route_model(self, task_type: TaskType | str) -> str:
        """Route task complexity to the optimal Bedrock model."""
        normalized = str(task_type).lower()
        if normalized in (TaskType.EXTRACTION, TaskType.TRIAGE):
            return self.fallback_model
        return self.primary_model

    def _normalize_prompt(self, prompt: str | list[dict[str, str]]) -> list[dict[str, str]]:
        """Normalize string prompt or message list to standardized message format."""
        if not prompt:
            raise LLMGatewayError(
                "Prompt cannot be empty", code="VALIDATION_ERROR", status_code=400
            )

        if isinstance(prompt, str):
            stripped = prompt.strip()
            if not stripped:
                raise LLMGatewayError(
                    "Prompt cannot be empty", code="VALIDATION_ERROR", status_code=400
                )
            return [{"role": "user", "content": stripped}]

        if isinstance(prompt, list):
            return prompt

        raise LLMGatewayError(
            f"Invalid prompt type: {type(prompt)}",
            code="VALIDATION_ERROR",
            status_code=400,
        )

    def _compute_cache_key(
        self, model: str, messages: list[dict[str, str]], temperature: float
    ) -> str:
        """Compute SHA-256 fingerprint for semantic / prompt caching."""
        serialized = json.dumps(
            {"model": model, "messages": messages, "temp": temperature},
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        """Clear the in-memory prompt cache."""
        with self._lock:
            self._cache.clear()

    def _record_metrics(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal,
        is_fallback: bool,
    ) -> None:
        """Update thread-safe cumulative cost and token metrics."""
        with self._lock:
            self._call_count += 1
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._total_cost_usd += cost_usd
            if is_fallback:
                self._fallback_count += 1

            if model not in self._model_breakdown:
                self._model_breakdown[model] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": Decimal("0.000000"),
                }

            entry = self._model_breakdown[model]
            entry["calls"] += 1
            entry["prompt_tokens"] += prompt_tokens
            entry["completion_tokens"] += completion_tokens
            entry["total_tokens"] += prompt_tokens + completion_tokens
            entry["cost_usd"] += cost_usd

    def get_cost_report(self) -> CostReport:
        """Return snapshot of token usage and financial cost ledger."""
        with self._lock:
            return CostReport(
                total_prompt_tokens=self._total_prompt_tokens,
                total_completion_tokens=self._total_completion_tokens,
                total_tokens=self._total_prompt_tokens + self._total_completion_tokens,
                total_cost_usd=self._total_cost_usd,
                call_count=self._call_count,
                fallback_count=self._fallback_count,
                cache_hit_count=self._cache_hit_count,
                model_breakdown={
                    k: {
                        "calls": v["calls"],
                        "prompt_tokens": v["prompt_tokens"],
                        "completion_tokens": v["completion_tokens"],
                        "total_tokens": v["total_tokens"],
                        "cost_usd": str(v["cost_usd"]),
                    }
                    for k, v in self._model_breakdown.items()
                },
            )

    def reset_cost_tracking(self) -> None:
        """Reset cost and token metrics to zero."""
        with self._lock:
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_cost_usd = Decimal("0.000000")
            self._call_count = 0
            self._fallback_count = 0
            self._cache_hit_count = 0
            self._model_breakdown.clear()

    def _generate_mock_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        task_type: TaskType | str,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, int, int]:
        """Generate deterministic offline mock responses without external calls."""
        content_input = messages[-1].get("content", "")
        task_str = str(task_type).lower()

        # Check if structured fixture should be served
        from src.llm.mock_client import get_mock_llm_client

        mock_client = get_mock_llm_client()
        target_schema = response_model or mock_client._infer_schema_from_prompt(content_input)
        if target_schema:
            fixture_text = mock_client._resolve_completion_content(
                content_input, response_model=target_schema
            )
            prompt_tokens = max(10, len(content_input) // 4)
            completion_tokens = max(15, len(fixture_text) // 4)
            return fixture_text, prompt_tokens, completion_tokens

        if task_str in (TaskType.EXTRACTION, TaskType.TRIAGE):
            mock_text = (
                f"[MOCK-{model}] Extracted entities: Supplier 'NanoCore Semiconductor', "
                f"Component 'MCU-X91', Disruption 'Cleanroom Fire', Severity 'HIGH'."
            )
        else:
            mock_text = (
                f"[MOCK-{model}] Synthesized incident analysis: NanoCore Semiconductor disruption "
                f"presents a critical bottleneck. Immediate spot-buy and secondary supplier qualification required."
            )

        prompt_tokens = max(10, len(content_input) // 4)
        completion_tokens = max(15, len(mock_text) // 4)
        return mock_text, prompt_tokens, completion_tokens

    async def acomplete(
        self,
        prompt: str | list[dict[str, str]],
        task_type: TaskType | str = TaskType.GENERAL,
        model: str | None = None,
        fallback_model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        use_cache: bool = True,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Asynchronously invoke LiteLLM completion with automated fallback and cost tracking."""
        start_time = time.perf_counter()
        trace_id = get_trace_id()
        messages = self._normalize_prompt(prompt)

        target_model = model or self.route_model(task_type)
        alt_model = fallback_model or (
            self.fallback_model if target_model == self.primary_model else self.primary_model
        )

        # 1. Semantic / Prompt Cache Check
        cache_key = self._compute_cache_key(target_model, messages, temperature)
        if use_cache:
            with self._lock:
                if cache_key in self._cache:
                    cached_res = self._cache[cache_key]
                    self._cache_hit_count += 1
                    logger.debug(
                        "Prompt cache hit for key %s (model %s)", cache_key[:8], target_model
                    )
                    return LLMResponse(
                        content=cached_res.content,
                        model=cached_res.model,
                        prompt_tokens=cached_res.prompt_tokens,
                        completion_tokens=cached_res.completion_tokens,
                        total_tokens=cached_res.total_tokens,
                        cost_usd=Decimal("0.000000"),
                        latency_ms=0.0,
                        is_fallback=cached_res.is_fallback,
                        is_cached=True,
                        trace_id=trace_id,
                        metadata={"cached": True, "cache_key": cache_key},
                    )

        # 2. Mock Mode (Zero live network calls)
        if self.use_mock:
            content, p_tok, c_tok = self._generate_mock_completion(
                messages, target_model, task_type, response_model=response_model
            )
            cost_usd = calculate_token_cost(target_model, p_tok, c_tok)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            response = LLMResponse(
                content=content,
                model=target_model,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=p_tok + c_tok,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                is_fallback=False,
                is_cached=False,
                trace_id=trace_id,
            )

            self._record_metrics(target_model, p_tok, c_tok, cost_usd, is_fallback=False)
            if use_cache:
                with self._lock:
                    self._cache[cache_key] = response
            return response

        # 3. Live Execution with Resilient Fallback
        is_fallback = False
        active_model = target_model
        raw_res = None

        try:
            raw_res = await litellm.acompletion(
                model=target_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except (
            RateLimitError,
            Timeout,
            APIConnectionError,
            APIError,
        ) as primary_exc:
            logger.warning(
                "Primary model %s failed (%s: %s); attempting fallback model %s [trace_id=%s]",
                target_model,
                type(primary_exc).__name__,
                primary_exc,
                alt_model,
                trace_id,
            )
            if alt_model and alt_model != target_model:
                try:
                    active_model = alt_model
                    is_fallback = True
                    raw_res = await litellm.acompletion(
                        model=alt_model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs,
                    )
                except Exception as fallback_exc:
                    logger.error(
                        "Fallback model %s also failed (%s: %s) [trace_id=%s]",
                        alt_model,
                        type(fallback_exc).__name__,
                        fallback_exc,
                        trace_id,
                    )
                    self._translate_and_raise(fallback_exc)
            else:
                self._translate_and_raise(primary_exc)
        except Exception as exc:
            self._translate_and_raise(exc)

        # 4. Extract Results and Compute Cost
        content = ""
        if raw_res and hasattr(raw_res, "choices") and raw_res.choices:
            choice = raw_res.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                content = choice.message.content or ""

        usage = getattr(raw_res, "usage", None)
        p_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
        c_tok = getattr(usage, "completion_tokens", 0) if usage else 0
        t_tok = getattr(usage, "total_tokens", p_tok + c_tok) if usage else (p_tok + c_tok)

        cost_usd = calculate_token_cost(active_model, p_tok, c_tok)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        response = LLMResponse(
            content=content,
            model=active_model,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=t_tok,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            is_fallback=is_fallback,
            is_cached=False,
            trace_id=trace_id,
            metadata={"raw_model": getattr(raw_res, "model", active_model)},
        )

        self._record_metrics(active_model, p_tok, c_tok, cost_usd, is_fallback=is_fallback)
        if use_cache:
            with self._lock:
                self._cache[cache_key] = response

        return response

    def complete(
        self,
        prompt: str | list[dict[str, str]],
        task_type: TaskType | str = TaskType.GENERAL,
        model: str | None = None,
        fallback_model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> LLMResponse:
        """Synchronously invoke LiteLLM completion."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an existing loop, execute in thread pool to prevent blocking
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run,
                    self.acomplete(
                        prompt=prompt,
                        task_type=task_type,
                        model=model,
                        fallback_model=fallback_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        use_cache=use_cache,
                        **kwargs,
                    ),
                ).result()

        return asyncio.run(
            self.acomplete(
                prompt=prompt,
                task_type=task_type,
                model=model,
                fallback_model=fallback_model,
                max_tokens=max_tokens,
                temperature=temperature,
                use_cache=use_cache,
                **kwargs,
            )
        )

    def _translate_and_raise(self, exc: Exception) -> None:
        """Translate third-party LiteLLM exceptions to standardized domain exceptions."""
        if isinstance(exc, RateLimitError) or "rate limit" in str(exc).lower():
            raise LLMRateLimitError(
                message=f"Rate limit exceeded: {exc}",
                details={"provider_error": str(exc)},
            ) from exc

        if isinstance(exc, Timeout) or "timeout" in str(exc).lower():
            raise LLMTimeoutError(
                message=f"LLM gateway timeout: {exc}",
                details={"provider_error": str(exc)},
            ) from exc

        if (
            isinstance(exc, APIConnectionError)
            or isinstance(exc, ServiceUnavailableError)
            or "connection" in str(exc).lower()
        ):
            raise LLMServiceUnavailableError(
                message=f"LLM service unavailable: {exc}",
                details={"provider_error": str(exc)},
            ) from exc

        if isinstance(exc, ContextWindowExceededError):
            raise LLMContextWindowExceededError(
                message=f"Context window exceeded: {exc}",
                details={"provider_error": str(exc)},
            ) from exc

        raise LLMGatewayError(
            message=f"LiteLLM invocation failed: {exc}",
            details={"provider_error": str(exc)},
        ) from exc


# ------------------------------------------------------------------------------
# Global Singleton Accessor
# ------------------------------------------------------------------------------

_gateway_singleton: LiteLLMGateway | None = None
_singleton_lock = threading.Lock()


def get_litellm_gateway(
    settings: Settings | None = None,
    use_mock: bool | None = None,
) -> LiteLLMGateway:
    """Return thread-safe singleton instance of LiteLLMGateway."""
    global _gateway_singleton
    with _singleton_lock:
        if _gateway_singleton is None:
            _gateway_singleton = LiteLLMGateway(settings=settings, use_mock=use_mock)
        return _gateway_singleton
