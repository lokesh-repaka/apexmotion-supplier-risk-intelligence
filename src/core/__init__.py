"""Core utilities, configuration, logging, and security for ApexMotion platform."""

from src.core.config import Settings, get_settings
from src.core.logging import bind_trace_id, get_logger, get_trace_id, setup_logging
from src.core.security import (
    ROLE_HIERARCHY,
    AuthenticatedUser,
    UserRole,
    create_access_token,
    get_current_user,
    require_any_role,
    require_role,
    validate_jwt_token,
)

__all__ = [
    "Settings",
    "get_settings",
    "setup_logging",
    "get_logger",
    "bind_trace_id",
    "get_trace_id",
    "UserRole",
    "ROLE_HIERARCHY",
    "AuthenticatedUser",
    "create_access_token",
    "validate_jwt_token",
    "get_current_user",
    "require_role",
    "require_any_role",
]
