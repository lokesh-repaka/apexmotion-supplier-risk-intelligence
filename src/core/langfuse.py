"""Langfuse LLM Telemetry & CallbackHandler Integration (P15-2).

Enforces:
- CallbackHandler integration on every LangGraph agent run (CLAUDE.md Sec 8.1)
- Prompt, completion, and total token usage tracking
- Strict Decimal precision for monetary cost calculation (BR-RULE-001)
- Investigation budget enforcement: agent cost <= $0.15 (CLAUDE.md Sec 13)
- Latency measurement across all graph execution steps
- Strict offline isolation (zero network I/O when USE_MOCK_LLM=true)
"""

from __future__ import annotations

import os
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from langchain_core.outputs import LLMResult
from langfuse.langchain import CallbackHandler

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("apexmotion.core.langfuse")

# Maximum permitted LLM inference cost per investigation ($0.15 USD)
INVESTIGATION_COST_BUDGET_USD = Decimal("0.1500")

# ------------------------------------------------------------------------------
# Model Pricing Table (USD per token in Decimal precision)
# ------------------------------------------------------------------------------
# Prices per 1,000,000 tokens:
# - Claude 3.5 Sonnet: $3.00 prompt / $15.00 completion -> $0.00000300 / $0.00001500
# - Claude 3.5 Haiku:  $0.80 prompt / $4.00 completion  -> $0.00000080 / $0.00000400
# - Llama 3.1 70B (self-hosted): $0.00 direct API cost
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    "claude-3-5-sonnet": {
        "prompt": Decimal("0.00000300"),
        "completion": Decimal("0.00001500"),
    },
    "claude-3-5-haiku": {
        "prompt": Decimal("0.00000080"),
        "completion": Decimal("0.00000400"),
    },
    "llama-3.1-70b": {
        "prompt": Decimal("0.00000000"),
        "completion": Decimal("0.00000000"),
    },
    "default": {
        "prompt": Decimal("0.00000300"),
        "completion": Decimal("0.00001500"),
    },
}


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
) -> Decimal:
    """Calculate exact LLM inference cost in USD using Decimal arithmetic.

    Args:
        prompt_tokens: Number of prompt/input tokens.
        completion_tokens: Number of generated completion tokens.
        model: Optional model identifier to resolve pricing tier.

    Returns:
        Exact Decimal cost quantized to 4 decimal places ($0.0001).
    """
    model_str = (model or "").lower()

    if "haiku" in model_str:
        rates = MODEL_PRICING["claude-3-5-haiku"]
    elif "llama" in model_str or "vllm" in model_str:
        rates = MODEL_PRICING["llama-3.1-70b"]
    elif "sonnet" in model_str:
        rates = MODEL_PRICING["claude-3-5-sonnet"]
    else:
        rates = MODEL_PRICING["default"]

    prompt_cost = Decimal(prompt_tokens) * rates["prompt"]
    completion_cost = Decimal(completion_tokens) * rates["completion"]
    total = prompt_cost + completion_cost
    return total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------------------
# ApexMotion Langfuse CallbackHandler
# ------------------------------------------------------------------------------


class ApexLangfuseCallbackHandler(CallbackHandler):
    """CallbackHandler instrumenting LangGraph investigations with Langfuse telemetry.

    Accumulates tokens, latency, and monetary cost per investigation workflow.
    Adheres strictly to BR-RULE-001 (Decimal currency math).
    """

    def __init__(
        self,
        trace_name: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        offline_mode: bool = False,
        public_key: str | None = None,
    ) -> None:
        self.trace_name = trace_name or "investigation.default"
        self.session_id = session_id
        self.user_id = user_id
        self.tags = list(tags) if tags else []
        self.metadata = dict(metadata) if metadata else {}
        self.offline_mode = offline_mode
        self._fallback_trace_id = f"lf-trace-{uuid.uuid4().hex[:16]}"

        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.tokens_used: int = 0
        self.cost_usd: Decimal = Decimal("0.0000")

        self.start_time: float = time.perf_counter()
        self.end_time: float | None = None
        self.latency_ms: int = 0
        self.errors: list[str] = []

        # Only pass public_key to super() when not in offline mode to avoid background network dispatch
        if not offline_mode and public_key:
            super().__init__(public_key=public_key)
        else:
            # Initialize empty or disabled LangchainCallbackHandler
            try:
                super().__init__()
            except Exception:
                pass

    def get_trace_id(self) -> str:
        """Return the Langfuse trace identifier or unique fallback ID."""
        lf_id = getattr(self, "last_trace_id", None)
        return str(lf_id) if lf_id else self._fallback_trace_id

    def record_tokens(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str | None = None,
    ) -> None:
        """Programmatically accumulate token consumption and recalculate cost."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.tokens_used += prompt_tokens + completion_tokens

        additional_cost = calculate_llm_cost(prompt_tokens, completion_tokens, model=model)
        self.cost_usd += additional_cost

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Callback fired when an LLM inference starts."""
        if not self.offline_mode:
            try:
                super().on_llm_start(
                    serialized,
                    prompts,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    tags=tags,
                    metadata=metadata,
                    **kwargs,
                )
            except Exception as exc:
                logger.debug("Langfuse on_llm_start error ignored: %s", exc)

    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        """Callback fired when LLM inference completes; extracts token counts and computes cost."""
        if not self.offline_mode:
            try:
                super().on_llm_end(response, **kwargs)
            except Exception as exc:
                logger.debug("Langfuse on_llm_end error ignored: %s", exc)

        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage") or {}
        model_name = llm_output.get("model_name") or "claude-3-5-sonnet"

        p_tokens = int(token_usage.get("prompt_tokens", 0))
        c_tokens = int(token_usage.get("completion_tokens", 0))

        if p_tokens > 0 or c_tokens > 0:
            self.record_tokens(p_tokens, c_tokens, model=model_name)
        elif llm_output.get("total_tokens"):
            # Fallback if only total_tokens is provided
            t_tokens = int(llm_output["total_tokens"])
            self.record_tokens(t_tokens, 0, model=model_name)

        self.latency_ms = int((time.perf_counter() - self.start_time) * 1000)

    def on_llm_error(
        self,
        error: BaseException,
        **kwargs: Any,
    ) -> None:
        """Callback fired on LLM inference error."""
        self.errors.append(str(error))
        if not self.offline_mode:
            try:
                super().on_llm_error(error, **kwargs)
            except Exception as exc:
                logger.debug("Langfuse on_llm_error error ignored: %s", exc)

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Callback fired when LangGraph StateGraph chain begins."""
        if not self.offline_mode:
            try:
                super().on_chain_start(
                    serialized,
                    inputs,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    tags=tags,
                    metadata=metadata,
                    **kwargs,
                )
            except Exception as exc:
                logger.debug("Langfuse on_chain_start error ignored: %s", exc)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Callback fired when LangGraph StateGraph chain terminates."""
        self.end_time = time.perf_counter()
        self.latency_ms = int((self.end_time - self.start_time) * 1000)

        if not self.offline_mode:
            try:
                super().on_chain_end(outputs, **kwargs)
            except Exception as exc:
                logger.debug("Langfuse on_chain_end error ignored: %s", exc)

    def get_metrics(self) -> dict[str, Any]:
        """Compile and return complete telemetry metrics dictionary."""
        current_latency = (
            self.latency_ms
            if self.end_time is not None
            else int((time.perf_counter() - self.start_time) * 1000)
        )
        return {
            "trace_id": self.get_trace_id(),
            "trace_name": self.trace_name,
            "session_id": self.session_id,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "budget_threshold_usd": INVESTIGATION_COST_BUDGET_USD,
            "is_cost_within_budget": self.cost_usd <= INVESTIGATION_COST_BUDGET_USD,
            "latency_ms": current_latency,
            "has_errors": len(self.errors) > 0,
            "last_error": self.errors[-1] if self.errors else None,
        }

    def flush(self) -> None:
        """Safely flush buffered Langfuse events."""
        if not self.offline_mode:
            try:
                client = getattr(self, "langfuse", None)
                if client is not None and hasattr(client, "flush"):
                    client.flush()
            except Exception as exc:
                logger.debug("Langfuse flush error ignored: %s", exc)


# ------------------------------------------------------------------------------
# Factory Function
# ------------------------------------------------------------------------------


def get_langfuse_callback_handler(
    alert_id: str | None = None,
    investigation_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    offline_mode: bool | None = None,
) -> ApexLangfuseCallbackHandler:
    """Instantiate and configure an ApexLangfuseCallbackHandler for an investigation.

    Args:
        alert_id: Associated alert identifier (used in trace_name).
        investigation_id: Unique investigation UUID or case identifier.
        user_id: Authenticated user initiating or executing the investigation.
        tags: Categorical tags for Langfuse filtering.
        metadata: Domain metadata dictionary (supplier_id, component_sku).
        offline_mode: Force offline mode without live network connection.

    Returns:
        Configured ApexLangfuseCallbackHandler.
    """
    settings = get_settings()

    # Determine offline isolation
    if offline_mode is not None:
        is_offline = offline_mode
    else:
        # Default to offline if mock LLM flag is set or keys are default local stubs
        pub_key = settings.LANGFUSE_PUBLIC_KEY
        is_offline = (
            settings.USE_MOCK_LLM
            or not pub_key
            or pub_key.startswith("pk-lf-1234567890")
            or os.environ.get("USE_MOCK_LLM", "").lower() in ("true", "1")
        )

    trace_name = (
        f"investigation.{alert_id}"
        if alert_id
        else f"investigation.{investigation_id or 'unknown'}"
    )
    combined_tags = list(tags) if tags else []
    if "langgraph" not in combined_tags:
        combined_tags.append("langgraph")
    if "supplier_risk" not in combined_tags:
        combined_tags.append("supplier_risk")

    pub_key_val = settings.LANGFUSE_PUBLIC_KEY if not is_offline else None

    return ApexLangfuseCallbackHandler(
        trace_name=trace_name,
        session_id=investigation_id or alert_id,
        user_id=user_id,
        tags=combined_tags,
        metadata=metadata,
        offline_mode=is_offline,
        public_key=pub_key_val,
    )


__all__ = [
    "INVESTIGATION_COST_BUDGET_USD",
    "ApexLangfuseCallbackHandler",
    "calculate_llm_cost",
    "get_langfuse_callback_handler",
]
