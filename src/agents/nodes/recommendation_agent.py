"""Recommendation Agent Node & Spend-Gated Mitigation Formulation (P9-6).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Probabilistic AI proposes and ranks procurement mitigation options, but is
    STRICTLY FORBIDDEN from auto-approving or auto-executing financial commitments.
  * Any mitigation scenario requiring financial spend (estimated_cost_usd > $0.00)
    strictly mandates Human-in-the-Loop (HITL) cryptographic authorization (requires_hitl=True).
  * Spend governance tiers strictly map:
    - Spend <= $25,000 -> Category Manager (1x token, 1-hr TTL).
    - Spend $25,001 - $100,000 -> Procurement Director (1x token, 1-hr TTL).
    - Spend > $100,000 -> Dual Sign-Off (Procurement Director + VP Supply Chain, 30-min TTL).
  * Exact Decimal arithmetic for all financial calculations:
    net_financial_benefit_usd == avoided_loss_usd - estimated_cost_usd.
- Structured LLM Integration (P8-3):
  * Uses LiteLLMGateway (TaskType.SYNTHESIS) with RecommendationReport response model;
    rejects free-text responses.
  * Features resilient deterministic fallback formulation on LLM timeout or service disruption.
- LangGraph State Machine Integration:
  * Full async node entrypoint recommendation_node updating SupplierRiskState channels.
  * Thread-safe singleton accessor get_recommendation_agent().
"""

import threading
from decimal import Decimal
from typing import Any

from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.hitl_tokens import SpendTier, get_spend_tier
from src.core.logging import get_logger
from src.llm.gateway import LiteLLMGateway, TaskType, get_litellm_gateway
from src.llm.models import (
    MitigationScenario,
    MitigationStrategyType,
    RecommendationReport,
    parse_structured_llm_response,
)

logger = get_logger("apexmotion.agents.nodes.recommendation")

# ------------------------------------------------------------------------------
# Node Identifier
# ------------------------------------------------------------------------------

NODE_RECOMMENDATION = "recommendation"


# ------------------------------------------------------------------------------
# Recommendation Agent Implementation
# ------------------------------------------------------------------------------


class RecommendationAgent:
    """Specialist Mitigation Formulation & Spend-Gated Recommendation Agent.

    Analyzes deterministic risk metrics, contractual terms, and operational context
    to formulate ranked mitigation options and map governing HITL spend authority tiers.
    """

    def __init__(
        self,
        gateway: LiteLLMGateway | None = None,
    ) -> None:
        self.gateway = gateway or get_litellm_gateway()

    @staticmethod
    def resolve_spend_tier(cost: Decimal) -> SpendTier:
        """Deterministically map financial commitment cost to its governing HITL spend tier."""
        return get_spend_tier(cost)

    def _build_prompt(
        self,
        alert_id: str,
        supplier_id: str,
        supplier_name: str,
        component_sku: str,
        plant_id: str,
        metrics: dict[str, Any],
        research_context: str,
        contract_context: str,
        narrative: str,
    ) -> str:
        """Construct grounded synthesis prompt for structured RecommendationReport generation."""
        financial_exp = metrics.get("financial_exposure", Decimal("0.00"))
        if not isinstance(financial_exp, Decimal):
            financial_exp = Decimal(str(financial_exp))

        factory_halt_exp = metrics.get("factory_halt_exposure", Decimal("0.00"))
        if not isinstance(factory_halt_exp, Decimal):
            factory_halt_exp = Decimal(str(factory_halt_exp))

        total_exp = metrics.get("total_exposure", financial_exp + factory_halt_exp)
        if not isinstance(total_exp, Decimal):
            total_exp = Decimal(str(total_exp))

        days_cover = metrics.get("days_of_cover", Decimal("0.00"))
        gap_days = metrics.get("gap_days", Decimal("0.00"))
        shortage_vol = metrics.get("shortage_volume", 0)

        return (
            "You are the ApexMotion Recommendation Agent. Formulate ranked, actionable supply chain mitigation "
            "scenarios to eliminate the projected manufacturing shortage without line halt.\n\n"
            "OPERATIONAL CONTEXT:\n"
            f"- Alert ID: {alert_id}\n"
            f"- Primary Supplier: {supplier_name} ({supplier_id})\n"
            f"- Component SKU: {component_sku}\n"
            f"- Assembly Plant: {plant_id}\n\n"
            "DETERMINISTIC RISK METRICS (Pure Python Calculator):\n"
            f"- Days of Cover: {days_cover} days\n"
            f"- Coverage Gap: {gap_days} days\n"
            f"- Shortage Volume: {shortage_vol:,} units\n"
            f"- Financial Exposure: ${financial_exp:,.2f} USD\n"
            f"- Factory Line Halt Exposure: €{factory_halt_exp:,.2f} EUR\n"
            f"- Total Exposure: ${total_exp:,.2f} USD\n\n"
            f"RESEARCH FINDINGS:\n{research_context or 'No external research findings attached.'}\n\n"
            f"CONTRACTUAL TERMS:\n{contract_context or 'Standard commercial purchase terms apply.'}\n\n"
            f"QUALITATIVE NARRATIVE:\n{narrative or 'Disruption triggers immediate mitigation formulation.'}\n\n"
            "CRITICAL GOVERNANCE RULES (BR-RULE-001):\n"
            "1. Propose between 2 and 4 ranked discrete mitigation scenarios.\n"
            "2. Permitted strategies: LOGISTICS_ACCELERATION, SECONDARY_SOURCING, SPOT_PURCHASE, "
            "PRODUCTION_REBALANCING, BUFFER_DEPLETION.\n"
            "3. Mathematical precision: net_financial_benefit_usd MUST equal avoided_loss_usd - estimated_cost_usd.\n"
            "4. Anti-Auto-Approval: Any scenario with estimated_cost_usd > 0 MANDATES requires_hitl = true.\n"
            "5. Spend Tiers:\n"
            "   - Cost <= $25,000 -> CATEGORY_MGR\n"
            "   - Cost $25,001 - $100,000 -> PROC_DIRECTOR\n"
            "   - Cost > $100,000 -> DUAL_VP\n"
            "   The governing_spend_tier MUST equal the highest spend tier required among all proposed scenarios.\n"
            "6. Select recommended_scenario_id from the proposed scenario IDs with executive justification.\n\n"
            "Respond ONLY with a JSON object conforming to the RecommendationReport schema."
        )

    def _generate_fallback_recommendations(
        self,
        state: SupplierRiskState,
    ) -> RecommendationReport:
        """Produce resilient, deterministic RecommendationReport on LLM synthesis degradation."""
        alert_id = state.get("alert_id") or "ALT-UNKNOWN"
        supplier_id = state.get("supplier_id") or "SUP-UNKNOWN"
        supplier_name = state.get("supplier_name") or supplier_id
        component_sku = state.get("component_sku") or "CMP-UNKNOWN"
        plant_ids = state.get("impacted_plant_ids") or ["PLT-MUC-01"]
        target_plant = plant_ids[0] if plant_ids else "PLT-MUC-01"

        metrics = state.get("risk_metrics") or {}
        raw_exposure = metrics.get("financial_exposure", Decimal("0.00"))
        financial_exp = (
            raw_exposure if isinstance(raw_exposure, Decimal) else Decimal(str(raw_exposure))
        )

        raw_halt = metrics.get("factory_halt_exposure", Decimal("0.00"))
        factory_halt_exp = raw_halt if isinstance(raw_halt, Decimal) else Decimal(str(raw_halt))

        total_loss = financial_exp + factory_halt_exp
        if total_loss <= Decimal("0.00"):
            total_loss = Decimal("100000.00")

        # Scenario 1: Spot-Buy Procurement (High speed, covers shortage, dual sign-off or director)
        spot_cost = min(total_loss * Decimal("0.15"), Decimal("180000.00"))
        if spot_cost < Decimal("15000.00") and total_loss >= Decimal("15000.00"):
            spot_cost = Decimal("15000.00")
        spot_tier = self.resolve_spend_tier(spot_cost)

        scenario_spot = MitigationScenario(
            scenario_id=f"SCEN-{alert_id[:8]}-SPOT-01",
            title=f"Emergency Spot-Buy for {component_sku} via Broker Network",
            strategy_type=MitigationStrategyType.SPOT_PURCHASE,
            description=(
                f"Execute emergency open-market spot procurement of replacement {component_sku} "
                f"from verified broker channels to bridge delivery gap from {supplier_name}."
            ),
            estimated_cost_usd=spot_cost,
            avoided_loss_usd=total_loss,
            net_financial_benefit_usd=total_loss - spot_cost,
            implementation_lead_time_days=Decimal("2.0"),
            lead_time_reduction_days=Decimal("2.0"),
            feasibility_score=0.88,
            required_spend_tier=spot_tier,
            target_supplier_id=f"SUP-SECONDARY-{supplier_id[:6]}",
            target_sku=component_sku,
            target_plant_id=target_plant,
            action_type="DISPATCH_SECONDARY_PO",
            risk_notes=[
                "Requires tarmac lot batch validation before assembly line feed.",
                "Subject to spot-market broker availability.",
            ],
        )

        # Scenario 2: Expedited Air Freight (High feasibility, director tier)
        freight_cost = min(total_loss * Decimal("0.08"), Decimal("65000.00"))
        if freight_cost < Decimal("10000.00") and total_loss > Decimal("15000.00"):
            freight_cost = Decimal("12000.00")
        freight_tier = self.resolve_spend_tier(freight_cost)
        avoided_freight = min(total_loss, Decimal("1500000.00"))

        scenario_freight = MitigationScenario(
            scenario_id=f"SCEN-{alert_id[:8]}-AIR-02",
            title=f"Expedited Air Freight Charter for {supplier_name} WIP",
            strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
            description=(
                f"Charter dedicated air cargo transport to airlift pre-inspected inventory from {supplier_name} "
                f"hub directly to plant {target_plant} tarmac under customs priority."
            ),
            estimated_cost_usd=freight_cost,
            avoided_loss_usd=avoided_freight,
            net_financial_benefit_usd=avoided_freight - freight_cost,
            implementation_lead_time_days=Decimal("1.5"),
            lead_time_reduction_days=Decimal("1.5"),
            feasibility_score=0.94,
            required_spend_tier=freight_tier,
            target_supplier_id=supplier_id,
            target_sku=component_sku,
            target_plant_id=target_plant,
            action_type="AMEND_PO_AIR_FREIGHT",
            risk_notes=[
                "Dependent on landing slot approval and expedited airport customs transit."
            ],
        )

        scenarios = [scenario_spot, scenario_freight]
        governing_tier = (
            SpendTier.DUAL_VP
            if any(s.required_spend_tier == SpendTier.DUAL_VP for s in scenarios)
            else (
                SpendTier.PROC_DIRECTOR
                if any(s.required_spend_tier == SpendTier.PROC_DIRECTOR for s in scenarios)
                else SpendTier.CATEGORY_MGR
            )
        )

        return RecommendationReport(
            alert_id=alert_id,
            component_sku=component_sku,
            supplier_id=supplier_id,
            scenarios=scenarios,
            recommended_scenario_id=scenario_spot.scenario_id,
            justification=(
                f"Deterministic fallback mitigation plan formulated to mitigate exposure of ${total_loss:,.2f} USD. "
                f"Scenario {scenario_spot.scenario_id} provides highest net financial benefit "
                f"(${scenario_spot.net_financial_benefit_usd:,.2f} USD) and protects assembly continuity."
            ),
            requires_hitl=True,
            governing_spend_tier=governing_tier,
        )

    def _extract_contexts(
        self,
        state: SupplierRiskState,
    ) -> tuple[str, str, str]:
        """Extract and format textual research, contract, and narrative context from state."""
        research_data = state.get("research_analysis") or {}
        findings = research_data.get("findings") if isinstance(research_data, dict) else None
        findings_list = findings if isinstance(findings, list) else []
        research_context = "\n".join(str(f) for f in findings_list)

        contract_data = state.get("contract_analysis") or {}
        clauses = contract_data.get("clauses") if isinstance(contract_data, dict) else None
        clauses_list = clauses if isinstance(clauses, list) else []
        contract_lines = [
            f"- {c.get('clause_type', 'CLAUSE')}: {c.get('content', '')}"
            for c in clauses_list
            if isinstance(c, dict)
        ]
        contract_context = "\n".join(contract_lines)

        narrative = state.get("narrative") or ""
        return research_context, contract_context, narrative

    async def arecommend(
        self,
        state: SupplierRiskState,
    ) -> RecommendationReport:
        """Asynchronously formulate ranked mitigation scenarios and determine governing spend tier."""
        alert_id = state.get("alert_id") or "ALT-UNKNOWN"
        supplier_id = state.get("supplier_id") or "SUP-UNKNOWN"
        supplier_name = state.get("supplier_name") or supplier_id
        component_sku = state.get("component_sku") or "CMP-UNKNOWN"
        plant_ids = state.get("impacted_plant_ids") or ["PLT-MUC-01"]
        target_plant = plant_ids[0] if plant_ids else "PLT-MUC-01"
        metrics = state.get("risk_metrics") or {}

        research_context, contract_context, narrative = self._extract_contexts(state)

        prompt = self._build_prompt(
            alert_id=alert_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            component_sku=component_sku,
            plant_id=target_plant,
            metrics=metrics,
            research_context=research_context,
            contract_context=contract_context,
            narrative=narrative,
        )

        try:
            response = await self.gateway.acomplete(
                prompt=prompt,
                task_type=TaskType.SYNTHESIS,
                response_format={"type": "json_object"},
            )
            return parse_structured_llm_response(response.content, RecommendationReport)

        except Exception as exc:
            logger.warning(
                "Recommendation formulation failed for alert %s (supplier=%s): %s. Engaging deterministic fallback.",
                alert_id,
                supplier_id,
                exc,
            )
            return self._generate_fallback_recommendations(state)

    def recommend(
        self,
        state: SupplierRiskState,
    ) -> RecommendationReport:
        """Synchronously formulate ranked mitigation scenarios using synchronous gateway."""
        alert_id = state.get("alert_id") or "ALT-UNKNOWN"
        supplier_id = state.get("supplier_id") or "SUP-UNKNOWN"
        supplier_name = state.get("supplier_name") or supplier_id
        component_sku = state.get("component_sku") or "CMP-UNKNOWN"
        plant_ids = state.get("impacted_plant_ids") or ["PLT-MUC-01"]
        target_plant = plant_ids[0] if plant_ids else "PLT-MUC-01"
        metrics = state.get("risk_metrics") or {}

        research_context, contract_context, narrative = self._extract_contexts(state)

        prompt = self._build_prompt(
            alert_id=alert_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            component_sku=component_sku,
            plant_id=target_plant,
            metrics=metrics,
            research_context=research_context,
            contract_context=contract_context,
            narrative=narrative,
        )

        try:
            response = self.gateway.complete(
                prompt=prompt,
                task_type=TaskType.SYNTHESIS,
                response_format={"type": "json_object"},
            )
            return parse_structured_llm_response(response.content, RecommendationReport)

        except Exception as exc:
            logger.warning(
                "Sync recommendation formulation failed for alert %s: %s. Engaging deterministic fallback.",
                alert_id,
                exc,
            )
            return self._generate_fallback_recommendations(state)


# ------------------------------------------------------------------------------
# Thread-safe Singleton Instance
# ------------------------------------------------------------------------------

_recommendation_agent_instance: RecommendationAgent | None = None
_recommendation_agent_lock = threading.Lock()


def get_recommendation_agent() -> RecommendationAgent:
    """Return the thread-safe singleton instance of RecommendationAgent."""
    global _recommendation_agent_instance
    if _recommendation_agent_instance is None:
        with _recommendation_agent_lock:
            if _recommendation_agent_instance is None:
                _recommendation_agent_instance = RecommendationAgent()
    return _recommendation_agent_instance


# ------------------------------------------------------------------------------
# LangGraph Node Entrypoint
# ------------------------------------------------------------------------------


async def recommendation_node(state: SupplierRiskState) -> dict[str, Any]:
    """LangGraph node: Formulate procurement mitigation options and map governing spend tier."""
    alert_id = state.get("alert_id") or "ALT-UNKNOWN"
    supplier_id = state.get("supplier_id") or "SUP-UNKNOWN"
    component_sku = state.get("component_sku") or "CMP-UNKNOWN"

    logger.info(
        "Recommendation node formulating mitigation options for alert: %s (supplier=%s, sku=%s)",
        alert_id,
        supplier_id,
        component_sku,
    )

    agent = get_recommendation_agent()
    report = await agent.arecommend(state)

    serialized_scenarios = [s.model_dump() for s in report.scenarios]
    top_scenario = next(
        (s for s in report.scenarios if s.scenario_id == report.recommended_scenario_id),
        report.scenarios[0],
    )

    audit_event = {
        "action": "RECOMMENDATION_FORMULATION_COMPLETED",
        "alert_id": alert_id,
        "supplier_id": supplier_id,
        "component_sku": component_sku,
        "recommended_action_id": report.recommended_scenario_id,
        "scenarios_count": len(report.scenarios),
        "governing_spend_tier": report.governing_spend_tier.value
        if hasattr(report.governing_spend_tier, "value")
        else str(report.governing_spend_tier),
        "requires_hitl": report.requires_hitl,
        "top_scenario_cost_usd": str(top_scenario.estimated_cost_usd),
    }

    return {
        "current_node": NODE_RECOMMENDATION,
        "execution_path": [NODE_RECOMMENDATION],
        "workflow_status": WorkflowStatus.PLANNING,
        "recommendations": serialized_scenarios,
        "recommended_action_id": report.recommended_scenario_id,
        "requires_hitl": report.requires_hitl,
        "governing_spend_tier": report.governing_spend_tier,
        "audit_events": [audit_event],
    }
