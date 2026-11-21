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
| **Phase 1 Progress** | 6 / 6 Tasks Completed | Completed ✅ |
| **Phase 2 Progress** | 5 / 5 Tasks Completed | Completed ✅ |
| **Phase 3 Progress** | 2 / 5 Tasks Completed | In Progress 🔄 |
| **Total Test Suites** | 13 (`test_project_structure.py`, `test_config.py`, `test_logging.py`, `test_api_skeleton.py`, `test_health_routes.py`, `test_ci_pipeline.py`, `test_docker_compose.py`, `test_localstack_bootstrap.py`, `test_redpanda_topics.py`, `test_neptune_emulation.py`, `test_makefile.py`, `test_database_models.py`, `test_database_migrations.py`) | PASSED ✅ |
| **Total Test Cases** | 83 unit/golden tests | 100% Passing (0 failures) |
| **Code Coverage (`src/`)** | **85%** statement coverage | Exceeds 80% DoD gate |
| **Active Branch** | `feature/database-schema-migrations` $\to$ `development` | Clean |

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
  - PR #3 merged into `development`.
- **P1-5 · Health Routes (`feature/api-health-routes`)**: Completed ✅
  - `src/api/routes/health.py`: Lightweight liveness probe (`GET /health`) with zero I/O and deep readiness probe (`GET /health/ready`) checking Aurora PostgreSQL, Amazon Neptune, Apache Kafka, and Redis.
  - Concurrency via `asyncio.gather()` and strict 2.0s probe timeout with latency tracking.
  - HTTP 503 status code returned when any downstream dependency is unhealthy.
  - 91% statement coverage on `src/api/routes/health.py`, 7 new unit tests (32 total).
  - PR #4 merged into `development`.
- **P1-6 · GitHub Actions CI Pipeline (`feature/ci-github-actions`)**: Completed ✅
  - `.github/workflows/ci.yml`: Multi-stage CI pipeline automating lint (`ruff`), type-check (`mypy`), offline tests with coverage gate (`pytest --cov-fail-under=80`), frontend build (`tsc && vite build`), and multi-stage container builds.
  - `Dockerfile.api`: Production Python 3.12-slim multi-stage image with non-root user (`appuser` UID 10001), healthcheck probe, and Uvicorn server.
  - `Dockerfile.worker`: Background LangGraph event consumer container with non-root execution.
  - `.dockerignore`: Excluded git, virtualenvs, bytecode, test caches, and secret credentials.
  - 6 new unit tests (38 total).
  - PR #5 merged into `development`.

### Phase 2: Local Dev Environment
- **P2-1 · Local Docker Compose (`feature/docker-compose-local`)**: Completed ✅
  - `docker-compose.yml`: Declared 5 local backing stores matching `.env.example`:
    - PostgreSQL 16 Alpine (`5432:5432`) with database healthcheck and persistent volume.
    - Redis 7 Alpine (`6379:6379`) with ping healthcheck and persistent volume.
    - Redpanda (`9092:9092`, `9644:9644`) with single-node flags and readiness probe.
    - LocalStack (`4566:4566`) with S3 and KMS emulation services.
    - Langfuse v2 (`3000:3000`) with PostgreSQL dependency health gating.
  - Isolated bridge network `apexmotion-network` and 4 named persistent volumes.
  - 5 new unit tests (43 total).
  - PR #6 merged into `development`.
- **P2-2 · LocalStack Bootstrap Script (`feature/localstack-bootstrap`)**: Completed ✅
  - `scripts/localstack_bootstrap.sh`: Bash script automating local cloud emulation setup:
    - S3 WORM audit bucket (`apexmotion-audit-worm`) with Object Lock in `COMPLIANCE` mode and 7-year retention policy (BR-RULE-007, FR-GOV-001).
    - S3 raw documents bucket (`apexmotion-raw-contracts`).
    - AWS KMS ECDSA P-256 signing key (`ECC_NIST_P256`, `SIGN_VERIFY`) with alias `alias/apexmotion-hitl-signer` for cryptographic HITL tokens (BR-RULE-001).
    - IAM role stubs (`apexmotion-api-role`, `apexmotion-worker-role`) with execution trust policies.
  - Idempotent execution and automatic mounting in `docker-compose.yml` (`/etc/localstack/init/ready.d/01-bootstrap.sh`).
  - 6 new unit tests (49 total).
  - PR #7 merged into `development`.
- **P2-3 · Redpanda Topic Creation Script (`feature/kafka-topic-setup`)**: Completed ✅
  - `scripts/redpanda_topics.sh`: Automated topic setup for the 4 core streaming event bus topics:
    - `supplier-events` (3 partitions, replication=1)
    - `risk-alerts` (3 partitions, replication=1)
    - `hitl-required` (3 partitions, replication=1)
    - `audit-events` (3 partitions, replication=1)
  - Auto-detection of local `rpk` CLI or running Docker container fallback (`apexmotion-redpanda`).
  - Idempotent topic existence checking and configurable broker address (`localhost:9092`).
  - 6 new unit tests (55 total).
  - PR #8 merged into `development`.
- **P2-4 · Neptune Local Emulation (`feature/neptune-local-emulation`)**: Completed ✅
  - `docker-compose.yml`: Added `neptune` service running `tinkerpop/gremlin-server:3.7.0` on port 8182 with container name `apexmotion-neptune`, healthcheck, and persistent volume `neptune_data`.
  - `scripts/neptune_seed.cypher`: Authored OpenCypher seed schema defining core nodes (`Supplier`, `Component`, `Assembly`, `Plant`, `Program`, `Contract`, `NewsEvent`, `GeopoliticalRisk`) and supply chain edges (`SUPPLIES`, `PART_OF_BOM`, `ASSEMBLED_AT`, `ALLOCATED_TO`, `TIER_1_OF`, `BOUND_BY`, `AFFECTS`, `THREATENS`), including NanoCore golden reference entities (`SUP-NC-882`, `MCU-X91`, `PLT-MUC-01`).
  - `scripts/neptune_smoke_test.sh`: Created executable bash script with strict error handling (`set -euo pipefail`), supporting `--dry-run` offline verification and live HTTP `/openCypher` / Gremlin query execution against port 8182.
  - 8 new unit tests in `tests/unit/test_neptune_emulation.py` (63 total passing tests across suite, 94% coverage).
  - PR #9 merged into `development`.
- **P2-5 · Developer Makefile (`feature/makefile-dev-commands`)**: Completed ✅
  - `Makefile`: Centralized developer automation defining `run-api`, `run-worker`, `run-frontend`, `test`, `test-unit`, `test-golden`, `test-coverage`, `lint`, `format`, `type-check`, `seed`, `up`, `down`, and `clean`.
  - Enforced strict offline isolation flags (`USE_LOCALSTACK=true USE_MOCK_LLM=true USE_LOCAL_KAFKA=true`) within `test` and `test-coverage` targets.
  - 6 new unit tests in `tests/unit/test_makefile.py` (69 total passing tests across suite, 94% coverage).
  - PR #10 merged into `development`.

### Phase 3: Persistence Layer (Aurora PostgreSQL)
- **P3-1 · SQLAlchemy 2.0 Async Models (`feature/database-sqlalchemy-models`)**: Completed ✅
  - `src/database/models.py`: Implemented DeclarativeBase and 5 core operational models matching CLAUDE.md Section 9:
    - `Supplier` (`suppliers`): UUID primary key, CheckConstraints on `tier` (1..3) and `risk_score` (0..1), unique `neptune_node_id`.
    - `RiskAlert` (`risk_alerts`): CheckConstraint on `risk_level` (CRITICAL, HIGH, MEDIUM, LOW), `days_of_cover` (NUMERIC 8,2), `financial_exposure` (NUMERIC 14,2 Decimal precision).
    - `HITLApproval` (`hitl_approvals`): `amount_usd` (NUMERIC 14,2), `spend_tier` CheckConstraint, unique index on `token_hash` for cryptographic anti-replay protection.
    - `AuditLog` (`audit_logs`): Immutable forensic ledger with autoincrement ID, JSONB states, and before_update/before_delete event listeners strictly prohibiting mutation (BR-RULE-007).
    - `AgentRun` (`agent_runs`): Multi-agent execution telemetry, token usage, duration, and Langfuse trace link.
  - Cross-dialect portability: Native PostgreSQL types (`JSONB`, `ARRAY`) with fallback SQLite variants for offline unit testing.
  - 8 new unit tests in `tests/unit/test_database_models.py` including async in-memory SQLite schema validation (77 total passing tests across suite, 95% statement coverage).
  - PR #11 merged into `development`.
- **P3-2 · Database Schema DDL & Alembic Migration Baseline (`feature/database-schema-migrations`)**: Completed ✅
  - `schema.sql` and `src/database/schema.sql`: Full PostgreSQL DDL script creating all 5 operational tables (`suppliers`, `risk_alerts`, `hitl_approvals`, `audit_logs`, `agent_runs`) with UUID extensions (`uuid-ossp`, `pgcrypto`), performance indexes, check constraints (`tier`, `risk_score`, `risk_level`, `spend_tier`, `status`), foreign keys, monetary precision (`NUMERIC(14,2)`), unique anti-replay constraint on `hitl_approvals.token_hash`, and an append-only trigger on `audit_logs` preventing `UPDATE` and `DELETE` (BR-RULE-007).
  - `alembic.ini`: Repo root configuration mapping `script_location = src/database/migrations` and dynamic URL resolution.
  - `src/database/migrations/env.py`: Async/sync migration runner dynamically resolving `DATABASE_URL` from `src.core.config.get_settings()`, binding `target_metadata = Base.metadata`, with offline dialect normalization.
  - `src/database/migrations/script.py.mako`: Revision template.
  - `src/database/migrations/versions/0001_initial_schema.py`: Baseline initial migration declaring all 5 tables, indexes, constraints, foreign keys, and complete `upgrade()` and `downgrade()`.
  - 6 new unit tests in `tests/unit/test_database_migrations.py` validating DDL, alembic configuration, baseline revision, and offline SQL generation (`alembic upgrade head --sql`) (83 total passing tests across suite, 85% statement coverage).

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
6. **Liveness / Readiness Decoupling**:
   - Liveness probes (`/health`) never perform network or database I/O, preventing cascading pod crashloops.
7. **Least-Privilege Containers**:
   - Production Docker images strictly prohibit root execution, enforcing unprivileged `appuser` (UID 10001) runtime.
8. **Local Dev Store Isolation**:
   - Local backing stores operate on an isolated bridge network with memory bounding to guarantee reproducible local development without external cloud leakage.
9. **WORM Immutability (BR-RULE-007)**:
   - Audit trail archived into S3 Object Lock in COMPLIANCE mode with 7-year retention.
10. **Partitioned Event Ingestion**:
    - Real-time streams are pre-partitioned (3 partitions) to support high throughput (1.11M events/day) without consumer starvation.
11. **Knowledge Graph Topology Isolation**:
    - Graph database emulation operates on standard port 8182 within `apexmotion-network`, seed Cypher adheres strictly to golden multi-tier supply chain topology.
12. **Standardized Command Automation**:
    - Developer operations governed through a canonical Makefile, eliminating configuration drift and enforcing offline test flags.
13. **Relational Model Purity & Anti-Replay Security**:
    - Aurora PostgreSQL models strictly enforce `NUMERIC(14,2)` for financial calculations, unique constraints on cryptographic `token_hash`, and programmatic append-only enforcement on audit logs.
14. **Versioned Schema Baseline & Offline Migration Safety**:
    - Database schema versions tracked via Alembic baseline with offline SQL compilation support (`alembic upgrade head --sql`), dual upgrade/downgrade logic, and database-level trigger immutability.

---

## 5. Next Planned Tasks
- **Phase 3 — Persistence Layer (Aurora PostgreSQL)**:
  - **P3-3**: Repository layer — async CRUD for all five tables (`src/database/repositories/`).
  - **P3-4**: Redis caching layer (`src/database/cache.py`).
  - **P3-5**: Database seed script (`scripts/seed_db.py`).
