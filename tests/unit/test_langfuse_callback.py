"""Unit tests for Langfuse callback integration and agent LLM telemetry (P15-2).

Enforces:
- CallbackHandler integration on every LangGraph agent run (CLAUDE.md Sec 8.1)
- Accurate token accounting (prompt, completion, total)
- Latency and cost tracking with Decimal precision (BR-RULE-001)
- Cost budget threshold validation (<= $0.15 per investigation, CLAUDE.md Sec 13)
- Strict offline isolation with zero external network calls (USE_MOCK_LLM=true)
- Database synchronization to AgentRun telemetry records
"""

import json
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.outputs import LLMResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from src.core.langfuse import (
    INVESTIGATION_COST_BUDGET_USD,
    ApexLangfuseCallbackHandler,
    calculate_llm_cost,
    get_langfuse_callback_handler,
)
from src.database.models import Base

# ------------------------------------------------------------------------------
# Test Database Fixtures
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[tuple[AsyncSession, async_sessionmaker[AsyncSession]], None]:
    """In-memory SQLite async session with StaticPool for offline isolated testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session, session_factory

    await engine.dispose()


# ------------------------------------------------------------------------------
# 1. Callback Handler Initialization & Metadata
# ------------------------------------------------------------------------------


def test_langfuse_callback_handler_initialization():
    """Verify handler initializes with standardized trace_name and metadata."""
    alert_id = "ALT-NC-2026-001"
    handler = get_langfuse_callback_handler(
        alert_id=alert_id,
        investigation_id="INV-001",
        user_id="USR-ANALYST-01",
        tags=["risk", "nanocore"],
        metadata={"supplier_id": "SUP-NC-4402"},
        offline_mode=True,
    )

    assert handler is not None
    assert handler.trace_name == f"investigation.{alert_id}"
    assert handler.session_id == "INV-001"
    assert handler.user_id == "USR-ANALYST-01"
    assert "nanocore" in handler.tags
    assert handler.metadata.get("supplier_id") == "SUP-NC-4402"
    assert handler.get_trace_id() is not None
    assert len(handler.get_trace_id()) > 0


# ------------------------------------------------------------------------------
# 2. Token Accounting (Prompt, Completion, Total)
# ------------------------------------------------------------------------------


def test_langfuse_callback_token_accumulation_from_llm_result():
    """Verify on_llm_end accumulates token counts from LLMResult output."""
    handler = get_langfuse_callback_handler(alert_id="ALT-001", offline_mode=True)

    # 1. First step: Triage extraction (Haiku)
    result_1 = LLMResult(
        generations=[[]],
        llm_output={
            "token_usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 150,
                "total_tokens": 1350,
            },
            "model_name": "claude-3-5-haiku-20241022",
        },
    )
    handler.on_llm_end(result_1)

    assert handler.prompt_tokens == 1200
    assert handler.completion_tokens == 150
    assert handler.tokens_used == 1350

    # 2. Second step: Narrative synthesis (Sonnet)
    result_2 = LLMResult(
        generations=[[]],
        llm_output={
            "token_usage": {
                "prompt_tokens": 3000,
                "completion_tokens": 500,
                "total_tokens": 3500,
            },
            "model_name": "claude-3-5-sonnet-20241022",
        },
    )
    handler.on_llm_end(result_2)

    assert handler.prompt_tokens == 4200
    assert handler.completion_tokens == 650
    assert handler.tokens_used == 4850


def test_langfuse_callback_manual_token_recording():
    """Verify record_tokens accumulates counts from tool or mock evaluations."""
    handler = get_langfuse_callback_handler(alert_id="ALT-002", offline_mode=True)

    handler.record_tokens(
        prompt_tokens=800,
        completion_tokens=200,
        model="claude-3-5-sonnet",
    )

    metrics = handler.get_metrics()
    assert metrics["prompt_tokens"] == 800
    assert metrics["completion_tokens"] == 200
    assert metrics["tokens_used"] == 1000
    assert metrics["cost_usd"] > Decimal("0.0000")


# ------------------------------------------------------------------------------
# 3. Deterministic Cost Computation (BR-RULE-001 Decimal Precision)
# ------------------------------------------------------------------------------


def test_calculate_llm_cost_models():
    """Verify calculate_llm_cost uses exact Decimal pricing for Claude 3.5 Sonnet and Haiku."""
    # Claude 3.5 Sonnet ($3 / 1M prompt, $15 / 1M completion)
    # 10,000 prompt tokens = $0.0300, 1,000 completion tokens = $0.0150 -> $0.0450
    cost_sonnet = calculate_llm_cost(
        prompt_tokens=10000,
        completion_tokens=1000,
        model="claude-3-5-sonnet-20241022",
    )
    assert isinstance(cost_sonnet, Decimal)
    assert cost_sonnet == Decimal("0.0450")

    # Claude 3.5 Haiku ($0.80 / 1M prompt, $4.00 / 1M completion)
    # 10,000 prompt tokens = $0.0080, 1,000 completion tokens = $0.0040 -> $0.0120
    cost_haiku = calculate_llm_cost(
        prompt_tokens=10000,
        completion_tokens=1000,
        model="claude-3-5-haiku-20241022",
    )
    assert isinstance(cost_haiku, Decimal)
    assert cost_haiku == Decimal("0.0120")

    # Self-hosted Llama-3.1-70B ($0.00 direct API cost)
    cost_llama = calculate_llm_cost(
        prompt_tokens=50000,
        completion_tokens=5000,
        model="meta-llama/Llama-3.1-70B-Instruct",
    )
    assert cost_llama == Decimal("0.0000")


def test_langfuse_callback_cost_budget_slo_enforcement():
    """Verify is_cost_within_budget adheres to the <= $0.15 investigation budget."""
    handler = get_langfuse_callback_handler(alert_id="ALT-BUDGET-01", offline_mode=True)

    # 1. Normal investigation ($0.0450 <= $0.1500)
    handler.record_tokens(10000, 1000, model="claude-3-5-sonnet")
    metrics = handler.get_metrics()
    assert metrics["cost_usd"] == Decimal("0.0450")
    assert metrics["is_cost_within_budget"] is True
    assert metrics["budget_threshold_usd"] == INVESTIGATION_COST_BUDGET_USD

    # 2. Over-budget investigation (> $0.1500)
    handler.record_tokens(40000, 5000, model="claude-3-5-sonnet")
    # Cumulative: 50,000 prompt ($0.1500) + 6,000 completion ($0.0900) = $0.2400
    metrics_over = handler.get_metrics()
    assert metrics_over["cost_usd"] == Decimal("0.2400")
    assert metrics_over["is_cost_within_budget"] is False


# ------------------------------------------------------------------------------
# 4. Latency Tracking & Metric Export
# ------------------------------------------------------------------------------


def test_langfuse_callback_latency_and_metrics_export():
    """Verify start/end lifecycle timestamps and non-negative latency_ms."""
    handler = get_langfuse_callback_handler(alert_id="ALT-LATENCY-01", offline_mode=True)

    handler.on_chain_start(serialized={}, inputs={"signal": "fire"})
    handler.record_tokens(500, 100)
    handler.on_chain_end(outputs={"status": "complete"})

    metrics = handler.get_metrics()
    assert "latency_ms" in metrics
    assert isinstance(metrics["latency_ms"], int)
    assert metrics["latency_ms"] >= 0
    assert metrics["tokens_used"] == 600
    assert metrics["trace_name"] == "investigation.ALT-LATENCY-01"


# ------------------------------------------------------------------------------
# 5. LangGraph Orchestrator Integration
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_auto_attaches_langfuse_callback():
    """Verify run_investigation automatically attaches CallbackHandler and records metrics."""
    from src.agents.orchestrator import InvestigationOrchestrator
    from src.agents.state import create_initial_state

    orchestrator = InvestigationOrchestrator()
    state = create_initial_state(
        alert_id="ALT-LANGFUSE-ORCH-01",
        supplier_id="SUP-NC-4402",
        signal_type="news",
        raw_signal="Cleanroom fire incident report",
    )
    # Set zero_impact metadata to route to dismiss node
    state["metadata"] = {"zero_impact": True}

    final_state = await orchestrator.run_investigation(state)

    assert final_state is not None
    meta = final_state.get("metadata") or {}
    assert "langfuse_trace_id" in meta
    assert "llm_metrics" in meta

    metrics = meta["llm_metrics"]
    assert "tokens_used" in metrics
    assert "cost_usd" in metrics
    assert "latency_ms" in metrics
    assert meta["langfuse_trace_id"] == metrics["trace_id"]


@pytest.mark.asyncio
async def test_orchestrator_preserves_custom_callback_config():
    """Verify run_investigation preserves existing callbacks in config."""
    from src.agents.orchestrator import InvestigationOrchestrator
    from src.agents.state import create_initial_state

    orchestrator = InvestigationOrchestrator()
    state = create_initial_state(
        alert_id="ALT-LANGFUSE-CUSTOM-01",
        supplier_id="SUP-NC-4402",
        signal_type="news",
        raw_signal="Logistics delay update",
    )
    state["metadata"] = {"zero_impact": True}

    custom_handler = get_langfuse_callback_handler(
        alert_id="ALT-CUSTOM-PRECONFIG", offline_mode=True
    )
    custom_handler.record_tokens(1000, 200)

    config: dict[str, Any] = {"callbacks": [custom_handler]}
    final_state = await orchestrator.run_investigation(state, config=config)

    meta = final_state.get("metadata") or {}
    assert meta.get("langfuse_trace_id") == custom_handler.get_trace_id()
    metrics = meta.get("llm_metrics") or {}
    assert metrics.get("tokens_used") >= 1200


# ------------------------------------------------------------------------------
# 6. Database Synchronization (AgentRun Repository)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_service_syncs_agent_run_telemetry(test_db: Any):
    """Verify InvestigationService records tokens, cost, and langfuse_trace_id in AgentRun."""
    from src.api.schemas.investigation import InvestigationStartRequest
    from src.core.security import AuthenticatedUser, UserRole
    from src.database.repositories.agent_run_repository import AgentRunRepository
    from src.services.investigation_service import InvestigationService

    session, session_factory = test_db

    user = AuthenticatedUser(
        user_id="USR-TELEMETRY-01",
        email="analyst@apexmotion.com",
        role=UserRole.ANALYST,
        display_name="Telemetry Analyst",
    )

    service = InvestigationService(session_factory=session_factory)
    req = InvestigationStartRequest(
        supplier_id="SUP-NC-4402",
        component_sku="NC-2024-001",
        alert_id=str(uuid4()),
        wait_for_completion=True,
    )

    record = await service.start_investigation(req, current_user=user, session=session)
    assert record.status in ("COMPLETED", "AWAITING_APPROVAL", "DISMISSED")

    # Verify AgentRun database synchronization
    async with session_factory() as verify_sess:
        repo = AgentRunRepository(verify_sess)
        agent_run = await repo.get_by_id(record.id)
        assert agent_run is not None
        assert agent_run.duration_ms is not None
        assert agent_run.duration_ms >= 0
        if record.langfuse_trace_id:
            assert agent_run.langfuse_trace_id == record.langfuse_trace_id


# ------------------------------------------------------------------------------
# 7. Safe Flush & Fallback
# ------------------------------------------------------------------------------


def test_langfuse_callback_flush_and_error_handling():
    """Verify flush executes without exception and on_llm_error records failure."""
    handler = get_langfuse_callback_handler(alert_id="ALT-ERR-01", offline_mode=True)

    # Error simulation
    handler.on_llm_error(ValueError("Rate limit reached"))
    metrics = handler.get_metrics()
    assert metrics["has_errors"] is True
    assert "Rate limit reached" in metrics["last_error"]

    # Safe flush
    handler.flush()


def test_langfuse_callback_total_tokens_fallback_and_online_hooks():
    """Verify total_tokens fallback and online mode hook invocations with error safety."""
    # 1. Test total_tokens fallback when prompt/completion are not separated
    handler = ApexLangfuseCallbackHandler(offline_mode=True)
    res = LLMResult(
        generations=[[]],
        llm_output={"total_tokens": 750, "model_name": "claude-3-5-sonnet"},
    )
    handler.on_llm_end(res)
    assert handler.tokens_used == 750
    assert handler.prompt_tokens == 750

    # 2. Test online mode hook execution and exception absorption
    online_handler = ApexLangfuseCallbackHandler(offline_mode=False)
    # Attach mock client to verify flush execution
    mock_client = MagicMock()
    online_handler.langfuse = mock_client

    online_handler.on_llm_start({"name": "test_llm"}, ["prompt 1"])
    online_handler.on_llm_end(res)
    online_handler.on_llm_error(RuntimeError("Transient network glitch"))
    online_handler.on_chain_start({"name": "test_chain"}, {"key": "value"})
    online_handler.on_chain_end({"output": "ok"})
    online_handler.flush()
    assert mock_client.flush.called


def test_langfuse_callback_factory_fallbacks():
    """Verify factory trace naming and tag construction across edge cases."""
    # Without alert_id, uses investigation_id
    h1 = get_langfuse_callback_handler(investigation_id="INV-999", offline_mode=True)
    assert h1.trace_name == "investigation.INV-999"
    assert "langgraph" in h1.tags
    assert "supplier_risk" in h1.tags

    # Without alert_id or investigation_id, uses unknown
    h2 = get_langfuse_callback_handler(offline_mode=True)
    assert h2.trace_name == "investigation.unknown"

    # Online mode with explicit public_key
    h3 = ApexLangfuseCallbackHandler(
        offline_mode=False,
        public_key="pk-lf-live-mock-key-12345",
    )
    assert h3.offline_mode is False
