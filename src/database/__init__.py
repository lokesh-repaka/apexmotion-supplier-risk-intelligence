"""ApexMotion Database package.

Exports SQLAlchemy Declarative Base, operational models, session management, and repositories.
"""

from src.database.models import (
    AgentRun,
    AuditLog,
    Base,
    HITLApproval,
    InventorySnapshot,
    RiskAlert,
    Supplier,
)
from src.database.opensearch_client import OpenSearchClient
from src.database.repositories import (
    AgentRunRepository,
    AuditLogRepository,
    BaseRepository,
    HITLApprovalRepository,
    InventoryRepository,
    RiskAlertRepository,
    SupplierRepository,
    TokenReplayError,
)
from src.database.seed_dev import (
    PLANTS_CATALOG,
    RAW_COMPONENTS_CATALOG,
    RAW_SUPPLIERS_CATALOG,
    SeedDevResult,
    seed_database,
    verify_seed_integrity,
)
from src.database.session import (
    get_async_engine,
    get_async_session_factory,
    get_db_session,
)

__all__ = [
    "Base",
    "Supplier",
    "RiskAlert",
    "HITLApproval",
    "AuditLog",
    "AgentRun",
    "InventorySnapshot",
    "get_async_engine",
    "get_async_session_factory",
    "get_db_session",
    "BaseRepository",
    "OpenSearchClient",
    "SupplierRepository",
    "RiskAlertRepository",
    "HITLApprovalRepository",
    "TokenReplayError",
    "AuditLogRepository",
    "AgentRunRepository",
    "InventoryRepository",
    "seed_database",
    "verify_seed_integrity",
    "SeedDevResult",
    "PLANTS_CATALOG",
    "RAW_SUPPLIERS_CATALOG",
    "RAW_COMPONENTS_CATALOG",
]
