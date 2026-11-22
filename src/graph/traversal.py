"""Supplier graph traversal service for Amazon Neptune (P5-4).

Traverses multi-tier automotive supplier networks to resolve:
- Shortest-path disruption blast radius: Disrupted Supplier -> Affected SKUs/Components -> Consuming Assembly Plants -> Vehicle Programs.
- Canonical NanoCore golden scenario blast radius resolution (SUP-NC-882 -> MCU-X91 -> PLT-MUC-01).
- Direct and sub-assembly BOM plant consumption paths.
- Multi-tier chain traversal (Tier-N -> Tier-1 OEM direct suppliers).
- Single-source dependencies and bottleneck components.
- Geopolitical risk regional exposure.
- 2-hop ego-subgraph extraction for frontend topology visualization.

Enforces:
- Triad of Separation (BR-RULE-001): Zero probabilistic LLM calls, zero arithmetic.
- Parameterized Cypher queries via CypherQueryLibrary to prevent Cypher injection (SEC-024).
- Safe traversal depth and timeout limits preventing graph traversal exhaustion (SEC-027).
- Exception mapping from low-level Neptune errors to domain TraversalError.
"""

from dataclasses import dataclass, field
from typing import Any

from src.api.exceptions import AppException
from src.core.logging import get_logger
from src.graph.neptune_client import (
    NeptuneCircuitBreakerOpenError,
    NeptuneClient,
    NeptuneClientError,
    NeptuneConnectionError,
    NeptuneQueryError,
    NeptuneTimeoutError,
)
from src.graph.queries import CypherQueryLibrary

logger = get_logger("apexmotion.graph.traversal")


class TraversalError(AppException):
    """Exception raised when graph traversal operations fail."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Any = None,
    ) -> None:
        super().__init__(
            code="GRAPH_TRAVERSAL_ERROR",
            message=message,
            status_code=status_code,
            details=details,
        )


@dataclass
class AffectedComponent:
    """Component impacted by a supplier disruption."""

    component_id: str
    mpn: str
    criticality: str
    days_of_cover: float | None = None
    sku: str | None = None
    description: str | None = None
    daily_consumption_rate: float | None = None
    relationship_type: str | None = None
    contract_id: str | None = None
    is_single_source: bool = False
    lead_time_days: int = 0


@dataclass
class AffectedPlant:
    """Assembly plant whose manufacturing line consumes an affected component."""

    plant_id: str
    plant_name: str
    rate_eur: float | None = None
    hourly_downtime_rate_usd: float | None = None
    location: str | None = None
    country: str | None = None
    region: str | None = None
    capacity: int | None = None
    component_id: str | None = None
    mpn: str | None = None


@dataclass
class AffectedProgram:
    """Vehicle production program associated with an assembly plant."""

    program_id: str
    model: str
    daily_target_units: int | None = None
    margin_per_unit_usd: float | None = None


@dataclass
class TierChain:
    """Multi-tier supplier relationship path up to Tier-1 direct suppliers."""

    sub_tier_id: str
    sub_tier_name: str
    sub_tier_level: int
    tier_1_id: str
    tier_1_name: str
    tier_1_level: int
    chain_depth: int
    supplier_chain: list[str] = field(default_factory=list)


@dataclass
class DisruptionBlastRadius:
    """Aggregated blast radius resulting from a supplier disruption."""

    supplier_id: str
    supplier_name: str | None = None
    supplier_risk_score: float | None = None
    shortest_path_hops: int = 0
    affected_components: list[AffectedComponent] = field(default_factory=list)
    affected_plants: list[AffectedPlant] = field(default_factory=list)
    affected_programs: list[AffectedProgram] = field(default_factory=list)
    tier_chains: list[TierChain] = field(default_factory=list)


@dataclass
class SingleSourceRisk:
    """Component bottleneck where single-source supplier dependency exists."""

    component_id: str
    mpn: str
    supplier_count: int
    supplier_ids: list[str] = field(default_factory=list)
    supplier_names: list[str] = field(default_factory=list)
    sku: str | None = None
    criticality: str | None = None
    days_of_cover: float | None = None


@dataclass
class GeopoliticalRiskExposure:
    """Regional and geopolitical risk exposure for a supplier or territory."""

    risk_id: str
    region: str
    risk_type: str
    severity: str
    supplier_id: str | None = None
    supplier_name: str | None = None
    supplier_country: str | None = None
    supplier_tier: int | None = None


@dataclass
class SupplierSubgraph:
    """Ego-subgraph representation around a supplier for graph visualization."""

    supplier_id: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DisruptionPath:
    """Full multi-hop disruption path from signal or sub-tier through to plant/program."""

    origin_id: str
    origin_type: str
    supplier_id: str
    supplier_name: str
    component_id: str
    mpn: str
    assembly_id: str | None = None
    assembly_name: str | None = None
    plant_id: str | None = None
    plant_name: str | None = None
    program_id: str | None = None
    program_model: str | None = None
    hop_count: int = 5
    path_nodes: list[str] = field(default_factory=list)


class SupplierTraversalService:
    """Graph traversal service for supplier impact analysis and risk blast radius."""

    def __init__(
        self,
        client: NeptuneClient | None = None,
        library: CypherQueryLibrary | None = None,
    ) -> None:
        """Initialize supplier traversal service.

        Args:
            client: Optional NeptuneClient instance. Defaults to new client.
            library: Optional CypherQueryLibrary instance. Defaults to standard library.
        """
        self._client = client or NeptuneClient()
        self._library = library or CypherQueryLibrary()

    def _map_exception(self, action: str, exc: Exception) -> TraversalError:
        """Map NeptuneClient exceptions into domain TraversalError."""
        status_code = 500
        if isinstance(exc, NeptuneTimeoutError):
            status_code = 504
        elif isinstance(exc, (NeptuneConnectionError, NeptuneCircuitBreakerOpenError)):
            status_code = 503
        elif isinstance(exc, NeptuneQueryError):
            status_code = 400
        elif isinstance(exc, NeptuneClientError):
            status_code = exc.status_code

        logger.error(
            "Graph traversal failure during '%s': %s (HTTP %d)",
            action,
            str(exc),
            status_code,
            exc_info=True,
        )
        return TraversalError(
            message=f"Failed to {action}: {exc}",
            status_code=status_code,
            details={"cause": str(exc), "action": action},
        )

    async def get_disruption_blast_radius(self, supplier_id: str) -> DisruptionBlastRadius:
        """Calculate the full disruption blast radius for a given supplier.

        Executes:
        - disruption_blast_radius: retrieves affected components, plants, and programs.
        - tier_chain_traversal: retrieves multi-tier chains linking this supplier to Tier-1s.

        Args:
            supplier_id: Target supplier identifier (e.g. 'SUP-NC-882').

        Returns:
            DisruptionBlastRadius containing affected components, plants, programs, and tier chains.

        Raises:
            TraversalError: If graph query or connection fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "disruption_blast_radius",
                {"supplier_id": supplier_id},
            )
            tier_records = await self._library.execute(
                self._client,
                "tier_chain_traversal",
                {"supplier_id": supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"calculate disruption blast radius for supplier {supplier_id}",
                exc,
            ) from exc

        supplier_name = None
        supplier_risk_score = None

        comp_map: dict[str, AffectedComponent] = {}
        plant_map: dict[str, AffectedPlant] = {}
        prog_map: dict[str, AffectedProgram] = {}

        for rec in records:
            if supplier_name is None and rec.get("supplier_name"):
                supplier_name = rec["supplier_name"]
            if supplier_risk_score is None and rec.get("supplier_risk_score") is not None:
                supplier_risk_score = float(rec["supplier_risk_score"])

            cid = rec.get("component_id")
            if cid and cid not in comp_map:
                comp_map[cid] = AffectedComponent(
                    component_id=cid,
                    mpn=rec.get("mpn", ""),
                    criticality=rec.get("component_criticality", "UNKNOWN"),
                    days_of_cover=(
                        float(rec["days_of_cover"])
                        if rec.get("days_of_cover") is not None
                        else None
                    ),
                )

            pid = rec.get("plant_id")
            if pid and pid not in plant_map:
                plant_map[pid] = AffectedPlant(
                    plant_id=pid,
                    plant_name=rec.get("plant_name", ""),
                    rate_eur=(
                        float(rec["plant_rate_eur"])
                        if rec.get("plant_rate_eur") is not None
                        else None
                    ),
                    hourly_downtime_rate_usd=(
                        float(rec["hourly_downtime_rate_usd"])
                        if rec.get("hourly_downtime_rate_usd") is not None
                        else None
                    ),
                )

            prg_id = rec.get("program_id")
            if prg_id and prg_id not in prog_map:
                prog_map[prg_id] = AffectedProgram(
                    program_id=prg_id,
                    model=rec.get("program_model", ""),
                )

        tier_chains: list[TierChain] = []
        for trec in tier_records:
            tier_chains.append(
                TierChain(
                    sub_tier_id=trec.get("sub_tier_id", ""),
                    sub_tier_name=trec.get("sub_tier_name", ""),
                    sub_tier_level=int(trec.get("sub_tier_level", 0)),
                    tier_1_id=trec.get("tier_1_id", ""),
                    tier_1_name=trec.get("tier_1_name", ""),
                    tier_1_level=int(trec.get("tier_1_level", 1)),
                    chain_depth=int(trec.get("chain_depth", 0)),
                    supplier_chain=list(trec.get("supplier_chain", [])),
                )
            )

        # Compute shortest-path hops:
        # Supplier -> Component -> Plant = 2 hops
        # Supplier -> Component = 1 hop
        # None = 0 hops
        if plant_map:
            shortest_path_hops = 2
        elif comp_map:
            shortest_path_hops = 1
        else:
            shortest_path_hops = 0

        return DisruptionBlastRadius(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_risk_score=supplier_risk_score,
            shortest_path_hops=shortest_path_hops,
            affected_components=list(comp_map.values()),
            affected_plants=list(plant_map.values()),
            affected_programs=list(prog_map.values()),
            tier_chains=tier_chains,
        )

    async def get_affected_components(self, supplier_id: str) -> list[AffectedComponent]:
        """Retrieve all components supplied directly or indirectly by a supplier.

        Args:
            supplier_id: Target supplier identifier.

        Returns:
            List of AffectedComponent objects.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "supplier_to_components",
                {"supplier_id": supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve affected components for supplier {supplier_id}",
                exc,
            ) from exc

        components: list[AffectedComponent] = []
        for rec in records:
            components.append(
                AffectedComponent(
                    component_id=rec.get("component_id", ""),
                    mpn=rec.get("mpn", ""),
                    criticality=rec.get("criticality", "UNKNOWN"),
                    days_of_cover=(
                        float(rec["days_of_cover"])
                        if rec.get("days_of_cover") is not None
                        else None
                    ),
                    sku=rec.get("sku"),
                    description=rec.get("description"),
                    daily_consumption_rate=(
                        float(rec["daily_consumption_rate"])
                        if rec.get("daily_consumption_rate") is not None
                        else None
                    ),
                    relationship_type=rec.get("relationship_type"),
                    contract_id=rec.get("contract_id"),
                    is_single_source=bool(rec.get("is_single_source", False)),
                    lead_time_days=int(rec.get("lead_time_days", 0)),
                )
            )
        return components

    async def get_affected_plants(self, component_or_supplier_id: str) -> list[AffectedPlant]:
        """Retrieve all plants consuming a component or impacted by a supplier.

        Args:
            component_or_supplier_id: Component ID (e.g. 'CMP-MCU-X91') or Supplier ID.

        Returns:
            List of AffectedPlant objects.

        Raises:
            TraversalError: If graph query fails.
        """
        if component_or_supplier_id.startswith("SUP-"):
            blast = await self.get_disruption_blast_radius(component_or_supplier_id)
            return blast.affected_plants

        try:
            records = await self._library.execute(
                self._client,
                "component_to_plants",
                {"component_id": component_or_supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve affected plants for component {component_or_supplier_id}",
                exc,
            ) from exc

        plants: list[AffectedPlant] = []
        seen_plants: set[str] = set()
        for rec in records:
            pid = rec.get("plant_id")
            if pid and pid not in seen_plants:
                seen_plants.add(pid)
                plants.append(
                    AffectedPlant(
                        plant_id=pid,
                        plant_name=rec.get("plant_name", ""),
                        location=rec.get("location"),
                        country=rec.get("country"),
                        region=rec.get("region"),
                        hourly_downtime_rate_usd=(
                            float(rec["hourly_downtime_rate_usd"])
                            if rec.get("hourly_downtime_rate_usd") is not None
                            else None
                        ),
                        rate_eur=(
                            float(rec["rate_eur"]) if rec.get("rate_eur") is not None else None
                        ),
                        capacity=(
                            int(rec["capacity"]) if rec.get("capacity") is not None else None
                        ),
                        component_id=rec.get("component_id"),
                        mpn=rec.get("mpn"),
                    )
                )
        return plants

    async def get_tier_chain(self, supplier_id: str) -> list[TierChain]:
        """Retrieve multi-hop tier hierarchy from a sub-tier supplier up to Tier-1s.

        Args:
            supplier_id: Sub-tier supplier identifier.

        Returns:
            List of TierChain paths.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "tier_chain_traversal",
                {"supplier_id": supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve tier chain for supplier {supplier_id}",
                exc,
            ) from exc

        chains: list[TierChain] = []
        for trec in records:
            chains.append(
                TierChain(
                    sub_tier_id=trec.get("sub_tier_id", ""),
                    sub_tier_name=trec.get("sub_tier_name", ""),
                    sub_tier_level=int(trec.get("sub_tier_level", 0)),
                    tier_1_id=trec.get("tier_1_id", ""),
                    tier_1_name=trec.get("tier_1_name", ""),
                    tier_1_level=int(trec.get("tier_1_level", 1)),
                    chain_depth=int(trec.get("chain_depth", 0)),
                    supplier_chain=list(trec.get("supplier_chain", [])),
                )
            )
        return chains

    async def find_single_source_risks(
        self, supplier_id: str | None = None
    ) -> list[SingleSourceRisk]:
        """Identify components dependent on a single supplier or flagged as single-source.

        Args:
            supplier_id: Optional supplier ID to filter single-source components.

        Returns:
            List of SingleSourceRisk objects.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "single_source_dependencies",
            )
        except Exception as exc:
            raise self._map_exception(
                "identify single source dependencies",
                exc,
            ) from exc

        risks: list[SingleSourceRisk] = []
        for rec in records:
            sup_ids = list(rec.get("supplier_ids", []))
            if supplier_id and supplier_id not in sup_ids:
                continue
            risks.append(
                SingleSourceRisk(
                    component_id=rec.get("component_id", ""),
                    mpn=rec.get("mpn", ""),
                    sku=rec.get("sku"),
                    criticality=rec.get("criticality"),
                    days_of_cover=(
                        float(rec["days_of_cover"])
                        if rec.get("days_of_cover") is not None
                        else None
                    ),
                    supplier_count=int(rec.get("supplier_count", len(sup_ids))),
                    supplier_ids=sup_ids,
                    supplier_names=list(rec.get("supplier_names", [])),
                )
            )
        return risks

    async def get_geopolitical_exposure(
        self,
        supplier_id: str | None = None,
        risk_id: str | None = None,
    ) -> list[GeopoliticalRiskExposure]:
        """Retrieve geopolitical and regional risks threatening suppliers.

        Args:
            supplier_id: Optional supplier ID filter.
            risk_id: Optional risk ID filter.

        Returns:
            List of GeopoliticalRiskExposure objects.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "geopolitical_risk_exposure",
                {"supplier_id": supplier_id, "risk_id": risk_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve geopolitical exposure (supplier={supplier_id}, risk={risk_id})",
                exc,
            ) from exc

        exposures: list[GeopoliticalRiskExposure] = []
        for rec in records:
            exposures.append(
                GeopoliticalRiskExposure(
                    risk_id=rec.get("risk_id", ""),
                    region=rec.get("region", ""),
                    risk_type=rec.get("risk_type", ""),
                    severity=rec.get("severity", ""),
                    supplier_id=rec.get("supplier_id"),
                    supplier_name=rec.get("supplier_name"),
                    supplier_country=rec.get("supplier_country"),
                    supplier_tier=(
                        int(rec["supplier_tier"]) if rec.get("supplier_tier") is not None else None
                    ),
                )
            )
        return exposures

    async def get_supplier_subgraph(self, supplier_id: str) -> SupplierSubgraph:
        """Extract a 2-hop ego-subgraph around a supplier for graph visualization.

        Args:
            supplier_id: Center supplier node identifier.

        Returns:
            SupplierSubgraph containing deduplicated nodes and edges.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "supplier_subgraph",
                {"supplier_id": supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve supplier subgraph for {supplier_id}",
                exc,
            ) from exc

        node_map: dict[str, dict[str, Any]] = {}
        edge_set: set[tuple[str, str, str]] = set()
        edges: list[dict[str, Any]] = []

        def add_node(node: Any) -> None:
            if isinstance(node, dict):
                node_id = node.get("id") or str(sorted(node.items()))
                if node_id not in node_map:
                    node_map[node_id] = node

        def add_edge(edge: Any) -> None:
            if isinstance(edge, dict):
                src = str(edge.get("from", ""))
                dst = str(edge.get("to", ""))
                etype = str(edge.get("type", ""))
                key = (src, dst, etype)
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append(edge)

        for rec in records:
            if "s" in rec and rec["s"]:
                add_node(rec["s"])
            for n in rec.get("nodes_hop1", []):
                add_node(n)
            for n in rec.get("nodes_hop2", []):
                add_node(n)
            for e in rec.get("edges_hop1", []):
                add_edge(e)
            for e in rec.get("edges_hop2", []):
                add_edge(e)

        return SupplierSubgraph(
            supplier_id=supplier_id,
            nodes=list(node_map.values()),
            edges=edges,
        )

    async def get_five_hop_disruption_paths(self, supplier_id: str) -> list[DisruptionPath]:
        """Retrieve 5-hop disruption paths originating from incidents or sub-tier suppliers.

        Path: Incident/GeopoliticalThreat -> Supplier -> Component -> Assembly -> Plant -> Program.

        Args:
            supplier_id: Disrupted supplier identifier.

        Returns:
            List of DisruptionPath objects with hop_count=5.

        Raises:
            TraversalError: If graph query fails.
        """
        try:
            records = await self._library.execute(
                self._client,
                "five_hop_disruption_path",
                {"supplier_id": supplier_id},
            )
        except Exception as exc:
            raise self._map_exception(
                f"retrieve 5-hop disruption paths for supplier {supplier_id}",
                exc,
            ) from exc

        paths: list[DisruptionPath] = []
        for rec in records:
            paths.append(
                DisruptionPath(
                    origin_id=rec.get("origin_id", ""),
                    origin_type=rec.get("origin_type", ""),
                    supplier_id=rec.get("supplier_id", ""),
                    supplier_name=rec.get("supplier_name", ""),
                    component_id=rec.get("component_id", ""),
                    mpn=rec.get("mpn", ""),
                    assembly_id=rec.get("assembly_id"),
                    assembly_name=rec.get("assembly_name"),
                    plant_id=rec.get("plant_id"),
                    plant_name=rec.get("plant_name"),
                    program_id=rec.get("program_id"),
                    program_model=rec.get("program_model"),
                    hop_count=int(rec.get("hop_count", 5)),
                    path_nodes=list(rec.get("path_nodes", [])),
                )
            )
        return paths

    async def is_single_source(self, component_id: str) -> bool:
        """Check if a specific component has a single-source dependency.

        Args:
            component_id: Component ID (e.g. 'CMP-MCU-X91') or MPN.

        Returns:
            True if single-sourced, False if multi-sourced or redundant.
        """
        risks = await self.find_single_source_risks()
        return any(r.component_id == component_id or r.mpn == component_id for r in risks)

    async def get_component_source_redundancy(self, component_id: str) -> dict[str, Any]:
        """Evaluate supplier source redundancy for a component.

        Args:
            component_id: Component ID or MPN.

        Returns:
            Dictionary with component_id, is_single_source, supplier_count, supplier_ids, risk_tier.
        """
        risks = await self.find_single_source_risks()
        for r in risks:
            if r.component_id == component_id or r.mpn == component_id:
                return {
                    "component_id": r.component_id,
                    "mpn": r.mpn,
                    "is_single_source": True,
                    "supplier_count": r.supplier_count,
                    "supplier_ids": r.supplier_ids,
                    "supplier_names": r.supplier_names,
                    "risk_tier": "CRITICAL" if r.criticality == "CRITICAL" else "HIGH",
                }
        return {
            "component_id": component_id,
            "mpn": component_id,
            "is_single_source": False,
            "supplier_count": 2,
            "supplier_ids": [],
            "supplier_names": [],
            "risk_tier": "LOW",
        }
