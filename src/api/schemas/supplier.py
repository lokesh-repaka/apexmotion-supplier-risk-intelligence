"""Pydantic v2 schemas for Supplier API routes (P11-4).

Endpoints supported:
- GET /api/v1/suppliers/{id}/risk: Live composite risk metrics, exposure, and blast radius.
- GET /api/v1/suppliers/{id}/graph: 2-hop ego-subgraph topology for frontend network visualization.
- GET /api/v1/suppliers: Paginated supplier directory with tier and risk filtering.
- GET /api/v1/suppliers/{id}: Detail supplier profile.

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Monetary precision using Decimal (NUMERIC(14,2)); float arithmetic strictly prohibited.
- Strict Pydantic v2 validation with extra="forbid" (or extra="allow" on dynamic graph properties).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SupplierResponse(BaseModel):
    """Basic supplier profile response representation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Primary UUID of supplier entity")
    name: str = Field(description="Legal entity name of the supplier")
    country_code: str = Field(description="ISO-3166-1 alpha-2 country code (e.g. DE, TW, US)")
    tier: int = Field(
        ge=1, le=3, description="Supply chain tier: 1 (Direct OEM), 2 (Sub-tier), 3 (Raw materials)"
    )
    risk_score: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Composite supplier risk score between 0.000 and 1.000",
    )
    neptune_node_id: str | None = Field(
        default=None,
        description="Knowledge graph node identifier (e.g. SUP-NC-882)",
    )
    created_at: datetime = Field(description="Creation timestamp (UTC)")
    updated_at: datetime = Field(description="Last update timestamp (UTC)")


class SupplierListResponse(BaseModel):
    """Paginated collection of suppliers."""

    model_config = ConfigDict(extra="forbid")

    items: list[SupplierResponse] = Field(description="List of suppliers matching filter criteria")
    total: int = Field(ge=0, description="Total matching supplier records")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, le=100, description="Page size limit")
    total_pages: int = Field(ge=0, description="Total pages available")


class SupplierRiskResponse(BaseModel):
    """Live risk intelligence metrics for an individual supplier."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(description="Supplier UUID identifier")
    neptune_node_id: str | None = Field(
        default=None,
        description="Knowledge graph node identifier (e.g. SUP-NC-882)",
    )
    supplier_name: str = Field(description="Supplier legal name")
    country_code: str = Field(description="ISO 2-letter country code")
    tier: int = Field(description="Supply chain tier (1..3)")
    composite_risk_score: Decimal = Field(
        description="Current composite risk score (0.000 to 1.000)"
    )
    risk_level: str = Field(description="Categorical risk rating: CRITICAL, HIGH, MEDIUM, LOW")
    active_alerts_count: int = Field(
        default=0,
        ge=0,
        description="Count of currently active risk alerts for this supplier",
    )
    critical_alerts_count: int = Field(
        default=0,
        ge=0,
        description="Count of active CRITICAL severity alerts",
    )
    total_financial_exposure_usd: Decimal = Field(
        default=Decimal("0.00"),
        description="Aggregated financial exposure across active alerts in USD",
    )
    total_shortage_volume: int = Field(
        default=0,
        ge=0,
        description="Total projected component unit shortage volume across active alerts",
    )
    min_days_of_cover: Decimal | None = Field(
        default=None,
        description="Lowest inventory days of cover across active component alerts",
    )
    affected_skus: list[str] = Field(
        default_factory=list,
        description="List of component SKUs currently in disruption",
    )
    affected_plants: list[str] = Field(
        default_factory=list,
        description="List of assembly plant IDs impacted in the graph blast radius",
    )
    affected_programs: list[str] = Field(
        default_factory=list,
        description="List of vehicle programs impacted in the graph blast radius",
    )
    is_single_source: bool = Field(
        default=False,
        description="True if supplier provides single-sourced components with no secondary qualification",
    )
    evaluated_at: datetime = Field(
        description="UTC timestamp when live risk metrics were computed",
    )


class SubgraphNode(BaseModel):
    """Node in the supplier ego-subgraph."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Unique entity identifier in knowledge graph")
    label: str | None = Field(
        default=None,
        description="Primary node label: Supplier, Component, Assembly, Plant, Program, etc.",
    )


class SubgraphEdge(BaseModel):
    """Relationship edge in the supplier ego-subgraph."""

    model_config = ConfigDict(extra="allow")

    source: str = Field(
        alias="from",
        description="Source node identifier",
    )
    target: str = Field(
        alias="to",
        description="Target node identifier",
    )
    relationship_type: str = Field(
        alias="type",
        description="Cypher relationship type: SUPPLIES_PART, TIER_1_OF, CONSUMES, ASSEMBLES, etc.",
    )


class SupplierGraphResponse(BaseModel):
    """Two-hop ego-subgraph topology surrounding a supplier."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(description="Target supplier identifier")
    neptune_node_id: str = Field(description="Neptune knowledge graph center node identifier")
    nodes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Deduplicated list of graph nodes within 2 hops",
    )
    edges: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Deduplicated list of relationship edges within 2 hops",
    )
    total_nodes: int = Field(ge=0, description="Total node count in subgraph")
    total_edges: int = Field(ge=0, description="Total edge count in subgraph")
    hop_depth: int = Field(default=2, ge=1, le=3, description="Ego-network traversal radius")
