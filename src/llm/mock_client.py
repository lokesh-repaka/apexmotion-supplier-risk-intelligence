"""Mock LLM Client & Schema Fixture Engine (P8-5).

Architectural Invariants & Governance:
- Offline First Isolation (CLAUDE.md Sec 14 & Rule 8):
  * Unit tests and offline development environments execute with zero live Bedrock or external I/O.
  * Activated by USE_MOCK_LLM=true (or use_mock=True).
- Fixture Schema Compliance (P8-3 models):
  * Returns typed, schema-validated JSON fixtures for ResearchAnalysis, ContractAnalysis,
    RiskNarrative, RecommendationReport, and IncidentCaseDossier.
  * Adheres strictly to Pydantic v2 schemas with extra='forbid' and exact Decimal precision.
- Intelligent Schema Detection & Response Queuing:
  * Supports explicit response_model parameters or automatic schema inference from prompt context.
  * Provides FIFO response queuing and per-schema fixture overrides for deterministic golden scenario testing.
- Monitory & Cost Precision (BR-RULE-001):
  * Tracks simulated token consumption with exact Decimal('0.000000') USD compute cost.
"""

import json
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.core.logging import get_logger, get_trace_id
from src.llm.fixtures import FIXTURES_DIR
from src.llm.gateway import LLMResponse, TaskType
from src.llm.models import (
    ContractAnalysis,
    IncidentCaseDossier,
    RecommendationReport,
    ResearchAnalysis,
    RiskNarrative,
    parse_structured_llm_response,
)

logger = get_logger("apexmotion.llm.mock_client")

# ------------------------------------------------------------------------------
# Fixture Schema Mapping
# ------------------------------------------------------------------------------

FIXTURE_SCHEMAS: dict[type[BaseModel] | str, str] = {
    ResearchAnalysis: "research_analysis.json",
    "researchanalysis": "research_analysis.json",
    "research_analysis": "research_analysis.json",
    "research": "research_analysis.json",
    "news": "research_analysis.json",
    ContractAnalysis: "contract_analysis.json",
    "contractanalysis": "contract_analysis.json",
    "contract_analysis": "contract_analysis.json",
    "contract": "contract_analysis.json",
    RiskNarrative: "risk_narrative.json",
    "risknarrative": "risk_narrative.json",
    "risk_narrative": "risk_narrative.json",
    "narrative": "risk_narrative.json",
    "risk": "risk_narrative.json",
    RecommendationReport: "recommendation_report.json",
    "recommendationreport": "recommendation_report.json",
    "recommendation_report": "recommendation_report.json",
    "recommendation": "recommendation_report.json",
    "recommendations": "recommendation_report.json",
    "mitigation": "recommendation_report.json",
    IncidentCaseDossier: "incident_case_dossier.json",
    "incidentcasedossier": "incident_case_dossier.json",
    "incident_case_dossier": "incident_case_dossier.json",
    "dossier": "incident_case_dossier.json",
}


def _resolve_schema_filename(schema: type[BaseModel] | str) -> str:
    """Resolve a schema class or string identifier to its canonical fixture filename."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        if schema in FIXTURE_SCHEMAS:
            return FIXTURE_SCHEMAS[schema]
        key = schema.__name__.lower()
        if key in FIXTURE_SCHEMAS:
            return FIXTURE_SCHEMAS[key]
    elif isinstance(schema, str):
        normalized = schema.lower().strip()
        if normalized in FIXTURE_SCHEMAS:
            return FIXTURE_SCHEMAS[normalized]

    raise KeyError(f"Unsupported fixture schema: {schema}")


def load_fixture_json(schema: type[BaseModel] | str, fixtures_dir: Path | None = None) -> str:
    """Load canonical fixture JSON text for a specified Pydantic schema or identifier."""
    filename = _resolve_schema_filename(schema)
    base_dir = fixtures_dir or FIXTURES_DIR
    filepath = base_dir / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Fixture file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        return f.read().strip()


def get_fixture_model[T: BaseModel](schema: type[T], fixtures_dir: Path | None = None) -> T:
    """Load and validate a canonical Pydantic model instance from fixture JSON."""
    raw_json = load_fixture_json(schema, fixtures_dir=fixtures_dir)
    return parse_structured_llm_response(raw_json, schema)


# ------------------------------------------------------------------------------
# Mock LLM Client
# ------------------------------------------------------------------------------


class MockLLMClient:
    """High-fidelity mock LLM client serving validated schema fixtures for offline tests.

    Emulates LiteLLMGateway completions, returning realistic domain payloads matching
    the canonical NanoCore semiconductor disruption reference scenario.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model: str = "mock-claude-3-5-sonnet",
        simulated_latency_ms: float = 1.0,
        use_mock: bool = True,
        fixtures_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model
        self.simulated_latency_ms = simulated_latency_ms
        self.use_mock = use_mock
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR

        self._lock = threading.Lock()
        self._response_queue: list[str] = []
        self._fixture_overrides: dict[type[BaseModel] | str, str] = {}

        # Usage metrics
        self.call_count = 0
        self.total_tokens = 0
        self.total_cost_usd = Decimal("0.000000")

    def enqueue_response(self, response: str | LLMResponse | BaseModel) -> None:
        """Enqueue a custom response to be returned by the next completion call (FIFO)."""
        with self._lock:
            if isinstance(response, LLMResponse):
                self._response_queue.append(response.content)
            elif isinstance(response, BaseModel):
                self._response_queue.append(response.model_dump_json(indent=2))
            elif isinstance(response, str):
                self._response_queue.append(response)
            else:
                self._response_queue.append(str(response))

    def enqueue_responses(self, responses: list[Any]) -> None:
        """Enqueue multiple responses in sequential order."""
        for resp in responses:
            self.enqueue_response(resp)

    def clear_queue(self) -> None:
        """Empty the response queue."""
        with self._lock:
            self._response_queue.clear()

    def set_fixture(
        self,
        schema: type[BaseModel] | str,
        data: BaseModel | dict[str, Any] | str,
    ) -> None:
        """Dynamically override the default fixture for a specific schema."""
        with self._lock:
            if isinstance(data, BaseModel):
                self._fixture_overrides[schema] = data.model_dump_json(indent=2)
            elif isinstance(data, dict):
                self._fixture_overrides[schema] = json.dumps(data, indent=2)
            elif isinstance(data, str):
                self._fixture_overrides[schema] = data
            else:
                self._fixture_overrides[schema] = str(data)

    def reset_fixtures(self) -> None:
        """Clear all custom fixture overrides, restoring default canonical fixtures."""
        with self._lock:
            self._fixture_overrides.clear()

    def reset_metrics(self) -> None:
        """Reset simulated call counts and token usage meters."""
        with self._lock:
            self.call_count = 0
            self.total_tokens = 0
            self.total_cost_usd = Decimal("0.000000")

    def _extract_prompt_text(self, prompt: str | list[dict[str, str]]) -> str:
        """Extract flat string representation of incoming prompt or message list."""
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, list):
            parts = [msg.get("content", "") for msg in prompt if isinstance(msg, dict)]
            return " ".join(parts)
        return str(prompt)

    def _infer_schema_from_prompt(self, prompt_text: str) -> type[BaseModel] | None:
        """Contextually infer target Pydantic schema based on prompt domain terminology."""
        text_lower = prompt_text.lower()

        # Recommendation Report detection
        if any(
            kw in text_lower
            for kw in (
                "recommendationreport",
                "recommendation_report",
                "recommendation_agent",
                "mitigation scenarios",
                "mitigation options",
                "ranked mitigation",
                "recommendation report",
            )
        ):
            return RecommendationReport

        # Contract Analysis detection
        if any(
            kw in text_lower
            for kw in (
                "contractanalysis",
                "contract_analysis",
                "contract_agent",
                "payment terms",
                "force majeure",
                "delay penalty",
                "delay penalties",
                "contract clauses",
                "governing contract",
            )
        ):
            return ContractAnalysis

        # Risk Narrative detection
        if any(
            kw in text_lower
            for kw in (
                "risknarrative",
                "risk_narrative",
                "risk_agent",
                "executive summary and operational impact",
                "risk narrative",
                "runway and exposure commentary",
                "root cause analysis",
            )
        ):
            return RiskNarrative

        # Incident Case Dossier detection
        if any(
            kw in text_lower
            for kw in (
                "incidentcasedossier",
                "incident_case_dossier",
                "case dossier",
                "incident case dossier",
            )
        ):
            return IncidentCaseDossier

        # Research Analysis detection
        if any(
            kw in text_lower
            for kw in (
                "researchanalysis",
                "research_analysis",
                "research_agent",
                "news disruption",
                "incident category",
                "disruption details",
                "external intelligence",
            )
        ):
            return ResearchAnalysis

        return None

    def _resolve_completion_content(
        self,
        prompt_text: str,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Resolve next completion content from queue, explicit schema, inference, or default."""
        with self._lock:
            # 1. FIFO Response Queue Check
            if self._response_queue:
                return self._response_queue.pop(0)

            # 2. Explicit or Inferred Schema Check
            target_schema = response_model or self._infer_schema_from_prompt(prompt_text)
            if target_schema:
                # Check for active override
                if target_schema in self._fixture_overrides:
                    return self._fixture_overrides[target_schema]
                if (
                    isinstance(target_schema, type)
                    and target_schema.__name__.lower() in self._fixture_overrides
                ):
                    return self._fixture_overrides[target_schema.__name__.lower()]

                # Return canonical fixture JSON
                try:
                    return load_fixture_json(target_schema, fixtures_dir=self.fixtures_dir)
                except Exception as exc:
                    logger.warning(
                        "Failed to load canonical fixture for %s: %s", target_schema, exc
                    )

            # 3. Generic Unstructured Fallback
            return (
                f"[MOCK-{self.model}] Deterministic mock completion for prompt: "
                f"'{prompt_text[:60]}...'"
            )

    async def acomplete(
        self,
        prompt: str | list[dict[str, str]],
        response_model: type[BaseModel] | None = None,
        task_type: TaskType | str = TaskType.GENERAL,
        **kwargs: Any,
    ) -> LLMResponse:
        """Asynchronously return deterministic fixture or queued mock LLM completion."""
        return self.complete(
            prompt=prompt,
            response_model=response_model,
            task_type=task_type,
            **kwargs,
        )

    def complete(
        self,
        prompt: str | list[dict[str, str]],
        response_model: type[BaseModel] | None = None,
        task_type: TaskType | str = TaskType.GENERAL,
        **kwargs: Any,
    ) -> LLMResponse:
        """Synchronously return deterministic fixture or queued mock LLM completion."""
        prompt_text = self._extract_prompt_text(prompt)
        content = self._resolve_completion_content(
            prompt_text=prompt_text,
            response_model=response_model,
        )

        p_tok = max(10, len(prompt_text) // 4)
        c_tok = max(15, len(content) // 4)
        total_tok = p_tok + c_tok

        with self._lock:
            self.call_count += 1
            self.total_tokens += total_tok

        trace_id = get_trace_id()
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=total_tok,
            cost_usd=Decimal("0.000000"),
            latency_ms=self.simulated_latency_ms,
            is_fallback=False,
            is_cached=False,
            trace_id=trace_id,
            metadata={
                "mock": True,
                "provider": "mock_client",
                "task_type": str(task_type),
                "inferred_schema": response_model.__name__ if response_model else None,
                **kwargs,
            },
        )


# ------------------------------------------------------------------------------
# Singleton & Dependency Injection
# ------------------------------------------------------------------------------

_mock_client_lock = threading.Lock()
_global_mock_client: MockLLMClient | None = None


def get_mock_llm_client() -> MockLLMClient:
    """Return thread-safe singleton instance of MockLLMClient."""
    global _global_mock_client
    if _global_mock_client is None:
        with _mock_client_lock:
            if _global_mock_client is None:
                _global_mock_client = MockLLMClient()
    return _global_mock_client
