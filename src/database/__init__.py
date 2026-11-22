"""ApexMotion Database package.

Exports SQLAlchemy Declarative Base, operational models, session management, and repositories.
"""

from src.database.models import (
    AgentRun,
    AuditLog,
    Base,
    HITLApproval,
    RiskAlert,
    Supplier,
)
from src.database.opensearch_client import OpenSearchClient
from src.database.repositories import (
    AgentRunRepository,
    AuditLogRepository,
    BaseRepository,
    HITLApprovalRepository,
    RiskAlertRepository,
    SupplierRepository,
    TokenReplayError,
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
]
