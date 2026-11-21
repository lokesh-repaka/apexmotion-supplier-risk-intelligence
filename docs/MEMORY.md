# ApexMotion Supplier Risk Intelligence — Honest Memory

> Single persistent ledger recording verified project status, test metrics, and architectural decisions.

---

## 1. Project Overview
- **Project**: ApexMotion Supplier Risk Intelligence Platform
- **Lead FDE**: Lokesh
- **Delivery Partner**: EURON Consulting
- **Core Stack**: FastAPI, LangGraph, Aurora PostgreSQL, Neptune OpenCypher, Redis, MSK Kafka, Keycloak SSO, AWS KMS

---

## 2. Honest Status & Metrics

| Metric | Current Count | Status |
|---|---|---|
| **Phase 1 Progress** | 4 / 6 Tasks Completed | In Progress 🔄 |
| **Total Test Suites** | 4 (`test_project_structure.py`, `test_config.py`, `test_logging.py`, `test_api_skeleton.py`) | PASSED ✅ |
| **Total Test Cases** | 25 unit/golden tests | 100% Passing (0 failures) |
| **Code Coverage (`src/`)** | **95%** statement coverage | Exceeds 80% DoD gate |
| **Active Branch** | `feature/api-app-skeleton` $\to$ `development` | Clean |

---

## 3. Completed Tasks Summary

### Phase 1: Runtime Skeleton
- **P1-1 · Project Structure (`feature/project-bootstrap`)**: Completed ✅
  - Full 9-layer directory skeleton with package `__init__.py` modules.
  - `pyproject.toml` (Python 3.12+), `frontend/package.json` (React 18/Vite), `.env.example`, `.gitignore`.
  - Canonical NanoCore reference scenario in `tests/golden/nanocore_scenario.json`.
- **P1-2 · Centralised Settings (`feature/core-config-settings`)**: Completed ✅
  - `src/core/config.py` using `pydantic-settings` and `@lru_cache`.
  - Enforced `Decimal` for HITL thresholds (`$25k`, `$100k`) per BR-RULE-001.
  - Sensitive tokens protected via `SecretStr`.
  - PR #1 merged into `development`.
- **P1-3 · Structured JSON Logging (`feature/core-structured-logging`)**: Completed ✅
  - `src/core/logging.py` formatting single-line JSON logs with UTC ISO-8601 timestamps.
  - Distributed `trace_id` propagated via `contextvars`.
  - Automatic recursive PII redaction (emails, cards, phones, bearer tokens).
  - 99% statement coverage across 7 unit tests.
  - PR #2 merged into `development`.
- **P1-4 · FastAPI App Skeleton (`feature/api-app-skeleton`)**: Completed ✅
  - `src/api/main.py`: FastAPI app instantiation, async lifespan context manager, CORS middleware.
  - Request ID / Trace ID middleware propagating `X-Request-ID` and `X-Trace-ID` and binding contextvars.
  - Standardized error envelopes conforming to CLAUDE.md Section 10 (`AppException`, `RequestValidationError`, `StarletteHTTPException`, `Exception`).
  - Traceback masking on unhandled 500 exceptions to prevent internal credential disclosure.
  - 92% coverage on `src/api/main.py`, 8 new unit tests (25 total).

---

## 4. Architectural Invariants Enforced
1. **The Triad of Responsibility (BR-RULE-001)**:
   - 100% of risk math in deterministic Python (`Decimal` / `NUMERIC(14,2)`). Zero LLM math.
2. **Keycloak OIDC & RBAC**:
   - Standardized authentication on Keycloak JWT tokens.
3. **Data Redaction**:
   - Zero raw PII in application logs.
4. **Offline Isolation**:
   - 100% of unit tests execute offline using local mock flags (`USE_LOCALSTACK=true`, `USE_MOCK_LLM=true`, `USE_LOCAL_KAFKA=true`).
5. **Secure Error Envelopes**:
   - Error responses adhere to `{"error": {"code": ..., "message": ..., "trace_id": ...}}` with zero internal stack traces leaking to clients.

---

## 5. Next Planned Tasks
- **P1-5**: Health routes (`GET /health`, `GET /health/ready`).
- **P1-6**: GitHub Actions CI pipeline.
