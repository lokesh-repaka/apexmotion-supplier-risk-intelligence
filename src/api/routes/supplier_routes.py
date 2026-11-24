"""Supplier intelligence and graph topology API routes (P11-4).

Endpoints:
- GET /api/v1/suppliers/{id}/risk: Live composite risk metrics, financial exposure, and blast radius.
- GET /api/v1/suppliers/{id}/graph: 2-hop ego-subgraph topology for frontend network visualization.
- GET /api/v1/suppliers: Paginated supplier directory with tier, country, and risk filtering.
- GET /api/v1/suppliers/{id}: Detail supplier profile.

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Zero probabilistic LLM math; deterministic calculations and database aggregates.
  * Monetary precision using Decimal (NUMERIC(14,2)); float arithmetic strictly forbidden.
- RBAC Security Gates:
  * analyst+ authority required across all endpoints.
"""

import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import NotFoundException
from src.api.schemas.supplier import (
    SupplierGraphResponse,
    SupplierListResponse,
    SupplierResponse,
    SupplierRiskResponse,
)
from src.core.logging import get_logger
from src.core.security import AuthenticatedUser, UserRole, require_role
from src.database.models import RiskAlert, Supplier
from src.database.repositories.supplier_repository import SupplierRepository
from src.database.session import get_db_session
from src.graph.traversal import SupplierTraversalService, TraversalError

logger = get_logger("apexmotion.api.suppliers")

router = APIRouter(tags=["Suppliers & Knowledge Graph"])


# ------------------------------------------------------------------------------
# Dependency Providers & Helpers
# ------------------------------------------------------------------------------


def get_supplier_traversal_service() -> SupplierTraversalService:
    """Dependency provider for SupplierTraversalService (mockable in tests)."""
    return SupplierTraversalService()


async def _resolve_supplier(
    id_val: str,
    session: AsyncSession,
) -> Supplier | None:
    """Resolve a supplier entity by UUID, Neptune node ID, or exact name."""
    repo = SupplierRepository(session)
    clean_id = id_val.strip()

    # 1. Try parsing as UUID
    try:
        parsed_uuid = uuid.UUID(clean_id)
        supplier = await repo.get_by_id(parsed_uuid)
        if supplier is not None:
            return supplier
    except (ValueError, AttributeError):
        pass

    # 2. Try looking up by Neptune node ID
    supplier = await repo.get_by_neptune_node_id(clean_id)
    if supplier is not None:
        return supplier

    # 3. Try looking up by exact name
    return await repo.get_by_name(clean_id)


# ------------------------------------------------------------------------------
# 1. Supplier Directory: GET /api/v1/suppliers
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/suppliers",
    response_model=SupplierListResponse,
    status_code=status.HTTP_200_OK,
    summary="List paginated suppliers with tier and risk filtering",
)
async def list_suppliers(
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    tier: Annotated[
        int | None, Query(ge=1, le=3, description="Filter by tier (1, 2, or 3)")
    ] = None,
    country_code: Annotated[
        str | None, Query(max_length=2, description="Filter by ISO 2-letter country")
    ] = None,
    min_risk_score: Annotated[
        Decimal | None, Query(ge=0, le=1, description="Minimum risk score")
    ] = None,
) -> SupplierListResponse:
    """Retrieve paginated supplier master directory with multi-attribute filtering."""
    logger.debug(
        "Listing suppliers for user '%s' [page=%s, size=%s, tier=%s, country=%s]",
        current_user.user_id,
        page,
        page_size,
        tier,
        country_code,
    )

    stmt = select(Supplier)
    count_stmt = select(func.count(Supplier.id))

    if tier is not None:
        stmt = stmt.where(Supplier.tier == tier)
        count_stmt = count_stmt.where(Supplier.tier == tier)

    if country_code:
        cc_clean = country_code.strip().upper()
        stmt = stmt.where(Supplier.country_code == cc_clean)
        count_stmt = count_stmt.where(Supplier.country_code == cc_clean)

    if min_risk_score is not None:
        stmt = stmt.where(Supplier.risk_score >= min_risk_score)
        count_stmt = count_stmt.where(Supplier.risk_score >= min_risk_score)

    # Count
    total_res = await session.execute(count_stmt)
    total_count = int(total_res.scalar_one())

    # Pagination & Ordering
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Supplier.name.asc()).offset(offset).limit(page_size)

    result = await session.execute(stmt)
    suppliers = result.scalars().all()

    items = [
        SupplierResponse(
            id=str(s.id),
            name=s.name,
            country_code=s.country_code,
            tier=s.tier,
            risk_score=s.risk_score,
            neptune_node_id=s.neptune_node_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in suppliers
    ]

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    return SupplierListResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ------------------------------------------------------------------------------
# 2. Supplier Risk Metrics: GET /api/v1/suppliers/{id}/risk
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/suppliers/{supplier_id}/risk",
    response_model=SupplierRiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get live composite risk metrics, exposure, and blast radius for a supplier",
)
async def get_supplier_risk(
    supplier_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    traversal_service: Annotated[SupplierTraversalService, Depends(get_supplier_traversal_service)],
) -> SupplierRiskResponse:
    """Retrieve live risk intelligence metrics for a supplier.

    Aggregates:
    1. Relational composite risk score and tier attributes from Aurora PostgreSQL.
    2. Active risk alerts, financial exposure ($ USD), and minimum days of cover.
    3. Multi-tier blast radius (affected assembly plants and vehicle programs) from Neptune.
    """
    logger.debug("Retrieving supplier risk for '%s' (user: %s)", supplier_id, current_user.user_id)

    supplier = await _resolve_supplier(supplier_id, session)
    if supplier is None:
        raise NotFoundException(f"Supplier '{supplier_id}' not found.")

    # 1. Fetch active alerts for this supplier
    stmt = (
        select(RiskAlert)
        .where(RiskAlert.supplier_id == supplier.id)
        .where(RiskAlert.status.in_(["OPEN", "INVESTIGATING", "ACKNOWLEDGED"]))
    )
    result = await session.execute(stmt)
    active_alerts = result.scalars().all()

    active_count = len(active_alerts)
    critical_count = sum(1 for a in active_alerts if a.risk_level == "CRITICAL")
    total_exposure = sum(
        (a.financial_exposure for a in active_alerts if a.financial_exposure is not None),
        Decimal("0.00"),
    )
    total_shortage = sum(
        (a.shortage_volume for a in active_alerts if a.shortage_volume is not None),
        0,
    )

    cover_values = [a.days_of_cover for a in active_alerts if a.days_of_cover is not None]
    min_cover = min(cover_values) if cover_values else None

    affected_skus = sorted({a.component_sku for a in active_alerts if a.component_sku})

    # 2. Determine categorical risk level
    supplier_score = supplier.risk_score or Decimal("0.000")
    if critical_count > 0 or supplier_score >= Decimal("0.700"):
        risk_lvl = "CRITICAL"
    elif any(a.risk_level == "HIGH" for a in active_alerts) or supplier_score >= Decimal("0.500"):
        risk_lvl = "HIGH"
    elif any(a.risk_level == "MEDIUM" for a in active_alerts) or supplier_score >= Decimal("0.300"):
        risk_lvl = "MEDIUM"
    else:
        risk_lvl = "LOW"

    # 3. Query Neptune knowledge graph blast radius
    neptune_id = supplier.neptune_node_id or str(supplier.id)
    affected_plants: list[str] = []
    affected_programs: list[str] = []
    is_single_source = False

    try:
        blast_radius = await traversal_service.get_disruption_blast_radius(neptune_id)
        affected_plants = [p.plant_id for p in blast_radius.affected_plants if p.plant_id]
        affected_programs = [p.program_id for p in blast_radius.affected_programs if p.program_id]
        is_single_source = any(c.is_single_source for c in blast_radius.affected_components)
    except Exception as exc:
        logger.warning(
            "Graph traversal blast radius lookup skipped for supplier '%s': %s",
            supplier.id,
            exc,
        )

    return SupplierRiskResponse(
        supplier_id=str(supplier.id),
        neptune_node_id=supplier.neptune_node_id,
        supplier_name=supplier.name,
        country_code=supplier.country_code,
        tier=supplier.tier,
        composite_risk_score=supplier_score,
        risk_level=risk_lvl,
        active_alerts_count=active_count,
        critical_alerts_count=critical_count,
        total_financial_exposure_usd=total_exposure,
        total_shortage_volume=total_shortage,
        min_days_of_cover=min_cover,
        affected_skus=affected_skus,
        affected_plants=sorted(set(affected_plants)),
        affected_programs=sorted(set(affected_programs)),
        is_single_source=is_single_source,
        evaluated_at=datetime.now(UTC),
    )


# ------------------------------------------------------------------------------
# 3. Supplier Subgraph: GET /api/v1/suppliers/{id}/graph
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/suppliers/{supplier_id}/graph",
    response_model=SupplierGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract 2-hop ego-subgraph topology surrounding a supplier for frontend visualization",
)
async def get_supplier_graph(
    supplier_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    traversal_service: Annotated[SupplierTraversalService, Depends(get_supplier_traversal_service)],
    max_hops: Annotated[int, Query(ge=1, le=3, description="Ego-network hop radius (1..3)")] = 2,
) -> SupplierGraphResponse:
    """Extract a 2-hop ego-subgraph around a target supplier node.

    Used by the frontend Supplier Graph Visualizer to render force-directed D3 / React Flow graphs.
    """
    logger.debug(
        "Extracting supplier graph for '%s' (hops=%s, user: %s)",
        supplier_id,
        max_hops,
        current_user.user_id,
    )

    supplier = await _resolve_supplier(supplier_id, session)
    if supplier is not None:
        target_neptune_id = supplier.neptune_node_id or str(supplier.id)
        supplier_uuid = str(supplier.id)
    else:
        target_neptune_id = supplier_id.strip()
        supplier_uuid = supplier_id.strip()

    # Query Neptune knowledge graph
    try:
        subgraph = await traversal_service.get_supplier_subgraph(target_neptune_id)
    except TraversalError as exc:
        raise exc
    except Exception as exc:
        raise TraversalError(
            f"Failed to extract subgraph for supplier '{supplier_id}': {exc}",
            status_code=500,
        ) from exc

    nodes = subgraph.nodes
    edges = subgraph.edges

    # If Neptune returned empty graph and supplier wasn't in DB either, 404
    if not nodes:
        if supplier is None:
            raise NotFoundException(
                f"Supplier '{supplier_id}' not found in knowledge graph or registry."
            )
        # Fallback: create root supplier node from DB entity
        nodes = [
            {
                "id": target_neptune_id,
                "label": "Supplier",
                "name": supplier.name,
                "tier": supplier.tier,
                "country": supplier.country_code,
            }
        ]
        edges = []

    return SupplierGraphResponse(
        supplier_id=supplier_uuid,
        neptune_node_id=target_neptune_id,
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        hop_depth=max_hops,
    )


# ------------------------------------------------------------------------------
# 4. Supplier Profile: GET /api/v1/suppliers/{id}
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed supplier profile by ID or Neptune node ID",
)
async def get_supplier_detail(
    supplier_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SupplierResponse:
    """Retrieve detailed master profile of an individual supplier."""
    logger.debug("Fetching supplier detail for '%s' (user: %s)", supplier_id, current_user.user_id)

    supplier = await _resolve_supplier(supplier_id, session)
    if supplier is None:
        raise NotFoundException(f"Supplier '{supplier_id}' not found.")

    return SupplierResponse(
        id=str(supplier.id),
        name=supplier.name,
        country_code=supplier.country_code,
        tier=supplier.tier,
        risk_score=supplier.risk_score,
        neptune_node_id=supplier.neptune_node_id,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )
