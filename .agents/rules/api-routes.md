---
trigger: glob
globs: **/src/api/**
---
# FastAPI Route Guidelines

- **Pydantic Validation**: All request and response bodies must enforce strict Pydantic v2 schemas.
- **Request Tracing**: Every route must propagate `request_id` / `trace_id` in headers and structured logs.
- **Authentication & RBAC**: Validate Keycloak JWT tokens (OIDC). Enforce `require_role()` on all protected routes.
- **Standard Error Format**: Return `{"error": {"code": str, "message": str, "trace_id": str}}`.
- **No Traceback Exposure**: Never leak internal exception traces or stack traces in HTTP responses.
- **No Business Logic**: Route handlers orchestrate validation, permissions, and invoke services or agents.
