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
| **Phase 3 Progress** | 5 / 5 Tasks Completed | Completed ✅ |
| **Phase 4 Progress** | 5 / 5 Tasks Completed | Completed ✅ |
| **Phase 5 Progress** | 5 / 5 Tasks Completed | Completed ✅ |
| **Phase 6 Progress** | 4 / 4 Tasks Completed | Completed ✅ |
| **Phase 7 Progress** | 5 / 5 Tasks Completed | Completed ✅ |
| **Phase 8 Progress** | 5 / 5 Tasks Completed (100%) | Completed ✅ |
| **Phase 9 Progress** | 6 / 6 Tasks Completed (100%) | Completed ✅ |
| **Phase 10 Progress** | 4 / 4 Tasks Completed (100%) | Completed ✅ |
| **Total Test Suites** | 50 (`test_project_structure.py`, `test_config.py`, `test_logging.py`, `test_api_skeleton.py`, `test_health_routes.py`, `test_ci_pipeline.py`, `test_docker_compose.py`, `test_localstack_bootstrap.py`, `test_redpanda_topics.py`, `test_neptune_emulation.py`, `test_makefile.py`, `test_database_models.py`, `test_database_migrations.py`, `test_database_repositories.py`, `test_token_hash_index.py`, `test_opensearch_client.py`, `test_security_rbac.py`, `test_hitl_tokens.py`, `test_demo_tokens.py`, `test_spend_tier_router.py`, `test_audit_writer.py`, `test_neptune_client.py`, `test_graph_seed.py`, `test_cypher_queries.py`, `test_supplier_traversal.py`, `test_graph_traversal_paths.py`, `test_kafka_consumer.py`, `test_kafka_producer.py`, `test_kafka_schemas.py`, `test_kafka_consumer_integration.py`, `test_risk_calculator.py`, `test_risk_scorer.py`, `test_inventory_service.py`, `test_alert_service.py`, `test_nanocore_golden.py`, `test_litellm_gateway.py`, `test_quarantined_reader.py`, `test_llm_models.py`, `test_vllm_client.py`, `test_mock_llm_client.py`, `test_agent_graph_skeleton.py`, `test_triage_agent.py`, `test_research_agent.py`, `test_contract_agent.py`, `test_risk_agent.py`, `test_recommendation_agent.py`, `test_hitl_service.py`, `test_dual_approval_enforcer.py`, `test_token_replay_guard.py`, `test_hitl_unit_tests.py`) | PASSED ✅ |
| **Total Test Cases** | 692 tests (673 unit + 11 integration + 8 golden) | 100% Passing (0 failures) |
| **Code Coverage (`src/`)** | **97.33%** statement coverage (`src/core/hitl_tokens.py` at 100%, `src/services/token_replay_guard.py` at 98%, `src/services/hitl_service.py` at 97%, `src/services/dual_approval_enforcer.py` at 93%, `src/agents/nodes/recommendation_agent.py` at 100% stmts / 100% branch, `src/agents/nodes/risk_agent.py`, `src/agents/nodes/contract_agent.py`, `src/agents/nodes/research_agent.py`, `src/agents/tools/research_tools.py`, `src/agents/nodes/triage_agent.py`, `src/agents/state.py`, `src/agents/graph.py`, `src/llm/`, `src/services/alert_service.py`, `src/services/risk/calculator.py`, `src/services/risk/scorer.py`, `src/kafka/handlers.py`, and `src/kafka/schemas/` at 100%; `src/database/repositories/risk_alert_repository.py` at 96%; `src/services/risk/inventory_service.py` at 92%) | Exceeds 80% DoD gate |
| **Active Branch** | `development` | Clean |

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
  - **CI Pipeline Stabilization (PR #47)**: Resolved GitHub Actions CI failures in `frontend` and `docker-build` jobs. Added `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, and minimal React application entrypoint (`src/main.tsx`, `src/App.tsx`). Fixed `Dockerfile.api` and `Dockerfile.worker` to copy `CLAUDE.md` and `src/` into the builder stage for hatchling metadata generation. All 5 CI jobs green.

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
  - PR #12 merged into `development`.
- **P3-3 · Repository Layer — Async CRUD for All Five Tables (`feature/database-repository-layer`)**: Completed ✅
  - `src/database/session.py`: Implemented singleton async engine, sessionmaker, and `get_db_session()` FastAPI dependency / context manager with transaction rollback and JSON serialization fallbacks for complex types.
  - `src/database/repositories/base.py`: Generic `BaseRepository[ModelType]` providing async CRUD (`create`, `get_by_id`, `list`, `count`, `update`, `delete`).
  - `src/database/repositories/supplier_repository.py`: `SupplierRepository` with queries by Neptune node ID, exact name, tier, country, high-risk threshold, and score updates.
  - `src/database/repositories/risk_alert_repository.py`: `RiskAlertRepository` with queries by supplier ID, SKU, status, active alerts (`OPEN` / `INVESTIGATING`), risk level, and status transitions.
  - `src/database/repositories/hitl_approval_repository.py`: `HITLApprovalRepository` with anti-replay lookup by `token_hash`, pending queue query, spend tier filtering, multi-signature logging (`record_signature`), and rejection handling.
  - `src/database/repositories/audit_log_repository.py`: `AuditLogRepository` strictly enforcing BR-RULE-007 immutability by overriding `update()` and `delete()` to raise `PermissionError`, plus entity, trace_id, and actor query methods.
  - `src/database/repositories/agent_run_repository.py`: `AgentRunRepository` with alert runs, Langfuse trace lookup, graph name queries, status filters, and run completion tracking.
  - 7 new unit tests in `tests/unit/test_database_repositories.py` (90 total passing tests across suite, 88.37% statement coverage).
  - PR #13 merged into `development`.
- **P3-4 · HITL Token Hash Unique Index & Anti-Replay Guard (`feature/database-token-hash-index`)**: Completed ✅
  - Synchronized canonical unique index name `idx_hitl_approvals_token_hash` across SQLAlchemy models ([src/database/models.py](file:///Users/lokeshrepaka/Desktop/FDE%20Project/src/database/models.py)), baseline migration ([src/database/migrations/versions/0001_initial_schema.py](file:///Users/lokeshrepaka/Desktop/FDE%20Project/src/database/migrations/versions/0001_initial_schema.py)), and PostgreSQL DDL (`schema.sql`).
  - Implemented `TokenReplayError`, `is_token_used()`, and `create_approval()` in [src/database/repositories/hitl_approval_repository.py](file:///Users/lokeshrepaka/Desktop/FDE%20Project/src/database/repositories/hitl_approval_repository.py) to provide defense-in-depth anti-replay interception before and during database transaction commits.
  - 6 new adversarial unit tests in `tests/unit/test_token_hash_index.py` verifying database-level `IntegrityError` enforcement, schema catalog index introspection, repository pre-validation, cross-alert token reuse denial, and DDL/migration index synchronization (96 total passing tests across suite, 88.15% statement coverage).
  - PR #14 merged into `development`.
- **P3-5 · Amazon OpenSearch Vector Search Client (`feature/database-opensearch-client`)**: Completed ✅
  - `src/database/opensearch_client.py`: Implemented asynchronous OpenSearch client supporting k-NN vector operations matching LLD Section 3.2:
    - HNSW cosine similarity index provisioning (`create_knn_index`) with 1536-dimensional vectors, `ef_construction=256`, and `m=16`.
    - Single and bulk document upserts (`upsert_document`, `bulk_upsert`) with automatic embedding vector binding.
    - Semantic k-nearest-neighbour vector search (`search_knn`) with optional boolean metadata filtering (`filter_criteria`) and minimum score thresholds.
    - Document retrieval and deletion (`get_document`, `delete_document`) with resilient 404 handling.
  - 9 new unit tests in `tests/unit/test_opensearch_client.py` covering index provisioning, upsert, bulk indexing, filtered k-NN vector queries, error resilience, and client connection cleanup (105 total passing tests across suite, 88.49% statement coverage).
  - PR #15 merged into `development`.

### Phase 4: Identity, Security & HITL Token Service
- **P4-1 · Okta JWT Validation & require_role() RBAC (`feature/security-okta-jwt-rbac`)**: Completed ✅
  - `src/core/security.py`: Implemented enterprise OIDC / Okta JWT validation and RBAC decorators:
    - User roles: `analyst`, `supply_chain_analyst`, `category_manager`, `procurement_director`, `vp_supply_chain`, `system_admin`.
    - Role hierarchy weights: `analyst` (10) < `category_manager` (20) < `procurement_director` (30) < `vp_supply_chain` (40) < `system_admin` (50).
    - `AuthenticatedUser` model with `has_role`, `has_any_role`, and `is_at_least` supporting role aliases (`analyst` <-> `supply_chain_analyst`) and hierarchical permission escalation.
    - Robust claim extraction across multiple standard OIDC/Okta/Keycloak claim structures (`roles`, `groups`, `realm_access.roles`, `scp`).
    - Standardized cryptographic JWT decoding and expiration validation (`validate_jwt_token`) raising `AuthenticationException` (401) on missing/invalid/expired tokens.
    - Reusable FastAPI dependencies: `get_current_user`, `require_role(required_role, allow_higher=True)`, and `require_any_role(*roles, allow_higher=True)` raising `AuthorizationException` (403) on under-privileged calls.
    - Development and test token generator `create_access_token` supporting custom claims, roles, and expiration TTL.
  - 12 new unit and integration tests in `tests/unit/test_security_rbac.py` verifying full token lifecycle, claims normalization, RBAC authorization, and FastAPI route responses (117 total passing tests across suite, 89.60% statement coverage).
- **P4-2 · AWS KMS ECDSA P-256 HITL Token Service (`feature/security-hitl-token-service`)**: Completed ✅
  - `src/core/hitl_tokens.py`: Implemented AWS KMS ECDSA P-256 token service with cryptographic signing and verification (ECC_NIST_P256, ECDSA_SHA_256):
    - Spend authority tiers: `CATEGORY_MGR` (<= $25,000, 1-hr TTL), `PROC_DIRECTOR` ($25,001 - $100,000, 1-hr TTL), and `DUAL_VP` (> $100,000, 30-min TTL) strictly enforcing `Decimal` precision per BR-RULE-001.
    - Deterministic canonical payload serialization (`action_id`, `alert_id`, `action_type`, `amount_usd`, `spend_tier`, `issued_at`, `expires_at`, `nonce`, `signer_id`, `signer_role`).
    - Cryptographic signature issuance and verification via AWS KMS with graceful ClientError exception trapping.
    - URL-safe Base64 serialization and deserialization with strict format validation.
    - Deterministic SHA-256 token hashing (`compute_token_hash`) for database-level anti-replay verification against `hitl_approvals.token_hash`.
    - Dual sign-off enforcement (`verify_dual_approval`) verifying two independently signed tokens with distinct signers bound to the same action ID.
  - 20 unit tests in `tests/unit/test_hitl_tokens.py` verifying all success and failure branches, achieving **100% statement and branch coverage** on `src/core/hitl_tokens.py` (137 total passing tests across suite, 91.37% statement coverage).
- **P4-3: Demo Okta tokens for platform personas** (`feature/security-demo-auth-tokens`):
  - Created domain model `DemoPersona` (`src/core/demo_auth.py`) with strict `Decimal` monetary spend limits adhering to BR-RULE-001 ($0 for analyst, $25,000 for category manager, $100,000 for procurement director, $2,500,000 dual-signoff for VP supply chain, system-only for admin).
  - Implemented in-memory `DEMO_PERSONAS` registry aligned with `CLAUDE.md` Section 3 and frontend UI mockup personas (Alex Chen, Priya Sharma, Klaus Weber, Dr. Elena Rostova, Alex Mercer).
  - Implemented `get_demo_persona` with role enum, string ID, and alias resolution (`supply_chain_analyst`, `cat_manager`, `director`, `vp`, `admin`).
  - Implemented `generate_demo_token` and `generate_all_demo_tokens` signing OIDC/Okta compliant JWTs populated with subject, email, name, role claims, and groups.
  - Authored CLI utility `scripts/generate_demo_tokens.py` supporting `text` console dashboard, `json` machine-readable output, and `env` shell variable export.
  - Exported demo persona models and utilities in `src/core/__init__.py`.
  - Added 6 comprehensive unit and integration tests in `tests/unit/test_demo_tokens.py` with 100% statement coverage on `src/core/demo_auth.py` (143 total passing tests across suite, 91.74% total coverage).
- **P4-4: Spend-tier router** (`feature/security-spend-tier-router`):
  - Created domain model `SpendTierRoute` and routing engine (`src/core/spend_tier_router.py`) enforcing BR-RULE-001 Decimal precision and rejecting native IEEE 754 float types.
  - Mapped action commitments deterministically to governance tiers:
    - Tier 1 (`CATEGORY_MGR`): Spend <= $25,000.00 (1x token, 1-hr TTL).
    - Tier 2 (`PROC_DIRECTOR`): Spend $25,000.01 - $100,000.00 (1x token, 1-hr TTL).
    - Tier 3 (`DUAL_VP`): Spend > $100,000.00 (Dual sign-off, 2x tokens, 30-min TTL, requiring distinct Procurement Director and VP Supply Chain signatures).
  - Implemented `can_user_approve_spend`, `is_eligible_signer`, `validate_approval_signers`, and `evaluate_spend_authorization` (raising 403 `AuthorizationException` on unauthorized attempts).
  - Exported router models and functions in `src/core/__init__.py`.
  - Added 13 unit tests in `tests/unit/test_spend_tier_router.py`, achieving **100% statement coverage** on `src/core/spend_tier_router.py` (156 total passing tests across suite, 92.54% total coverage).
- **P4-5: Append-only audit writer** (`feature/security-audit-writer`):
  - Implemented `src/core/audit.py` with `write_audit_log` and `AuditWriter` service class enforcing BR-RULE-007.
  - Enforced autonomous transaction execution: audit entries execute inside an independent, dedicated `AsyncSession`, guaranteeing persistence even when outer caller business transactions fail or are explicitly rolled back.
  - Implemented automatic distributed trace context propagation via `src.core.logging.get_trace_id()`.
  - Implemented deterministic UUID coercion (`coerce_uuid`) supporting string UUIDs and human-readable identifiers (`usr-alex-chen`, `sys-engine`).
  - Implemented recursive state payload sanitization (`sanitize_audit_payload`) automatically masking tokens, secrets, passwords, and private keys.
  - Provided forensic trail query helpers: `get_entity_audit_trail`, `get_trace_audit_trail`, and `get_actor_audit_trail`.
  - Added 7 unit tests in `tests/unit/test_audit_writer.py`, achieving **100% statement coverage** on `src/core/audit.py` (163 total passing tests across suite, 93.00% total coverage).
  - **Phase 4 (Identity, Security & HITL Token Service) is now 100% complete (5/5 tasks).**

### Phase 5: Knowledge Graph (Amazon Neptune)
- **P5-1 · Neptune OpenCypher Client (`feature/graph-neptune-client`)**: Completed ✅
  - `src/graph/neptune_client.py`: Implemented asynchronous Amazon Neptune OpenCypher client:
    - Bounded connection pooling via `httpx.AsyncClient` (`max_connections=100`, `max_keepalive_connections=20`, `keepalive_expiry=30.0s`).
    - Standardized OpenCypher execution via `POST /openCypher` with JSON parameter binding to prevent Cypher query injection (SEC-024).
    - Exponential backoff retry logic (LLD Section 6.1: 3 retries, $0.5s, 1.0s, 2.0s$) on transient HTTP codes (429, 500, 502, 503, 504) and network dropouts.
    - Immediate failure on client errors (400 Bad Request) without retry.
    - Strict 5.0-second query deadline raising `NeptuneTimeoutError` (`GRAPH_504_TIMEOUT`).
    - Circuit breaker pattern tracking consecutive failures/timeouts (threshold: 5) raising `NeptuneCircuitBreakerOpenError` (`GRAPH_CIRCUIT_BREAKER_OPEN`, 503) to prevent cascading resource starvation.
    - Distributed `trace_id` propagation in request headers (`X-Trace-ID`, `X-Request-ID`).
    - Cluster health check probe (`health_check`) executing `RETURN 1 AS ping`.
    - Injectable HTTP transport for 100% offline unit testing with zero external network or AWS dependencies.
  - Exported client and structured exception hierarchy in `src/graph/__init__.py`.
  - 14 comprehensive unit tests in `tests/unit/test_neptune_client.py` achieving **99% statement coverage** on `src/graph/neptune_client.py` (177 total passing tests across suite, 93.49% total coverage).
- **P5-2 · Graph Schema Seed (`feature/graph-schema-seed`)**: Completed ✅
  - `src/graph/seed.py`: Implemented idempotent OpenCypher Knowledge Graph schema seeder service:
    - Declared canonical models for core automotive entities (`Supplier`, `Component`, `Plant`, `Contract`, `NewsEvent`, `GeopoliticalRisk`, `Assembly`, `Program`).
    - Enforced supply chain relationships (`SUPPLIES`, `SUPPLIES_PART`, `USED_BY`, `TIER_1_OF`, `PART_OF_BOM`, `ASSEMBLED_AT`, `ALLOCATED_TO`, `BOUND_BY`, `AFFECTS`, `THREATENS`).
    - Fully represented the canonical NanoCore golden scenario: NanoCore (`SUP-NC-882`, Tier-2) supplying MCU-X91 (`CMP-MCU-X91`) to Munich Assembly Hub (`PLT-MUC-01`) via BetaElectro (`SUP-BE-101`, Tier-1) with Cleanroom fire event (`EVT-NEWS-2026-081`) and Taiwan export risk (`RISK-GEO-TW-01`).
    - `get_seed_cypher_statements`: Generates idempotent `MERGE` statements preventing entity duplication (SEC-025).
    - `seed_graph`: Asynchronously executes statements against `NeptuneClient` with optional graph purge (`clear_existing=True`), returning `SeedResult` metrics.
    - `verify_seed_integrity`: Automated audit report verifying all node labels, relationship counts, and presence of golden entities.
  - `scripts/seed_neptune.py`: CLI seeding tool supporting `--dry-run`, `--clear`, `--verify`, and host/port overrides.
  - Synchronized `scripts/neptune_seed.cypher` with matching idempotent `MERGE` statements.
  - 12 comprehensive unit tests in `tests/unit/test_graph_seed.py` achieving **97% statement coverage** on `src/graph/seed.py` (189 total passing tests across suite, 93.80% total coverage).
- **P5-3 · Named Cypher Query Library (`feature/graph-cypher-queries`)**: Completed ✅
  - `src/graph/queries/library.py`: Implemented centralized OpenCypher query registry and execution facade:
    - Declared canonical parameterized queries: `supplier_to_components`, `component_to_plants`, `tier_chain_traversal`, `disruption_blast_radius`, `single_source_dependencies`, `geopolitical_risk_exposure`, `supplier_subgraph`, `event_to_suppliers`, `plant_to_programs`.
    - Parameter contracts (`CypherQuery`) enforcing mandatory parameter checks and default value merging, eliminating dynamic string concatenation and preventing Cypher injection (`SEC-026`).
    - Standardized execution facade (`CypherQueryLibrary.execute`) passing parameters safely to `NeptuneClient`.
    - Exported named query templates, helper functions, and dictionary registry in `src/graph/queries/__init__.py` and `src/graph/__init__.py`.
  - 13 comprehensive unit tests in `tests/unit/test_cypher_queries.py` achieving **100% statement coverage** on `src/graph/queries/` (202 total passing tests across suite, 93.98% total coverage).
- **P5-4 · Supplier Traversal Service (`feature/graph-traversal-service`)**: Completed ✅
  - `src/graph/traversal.py`: Implemented `SupplierTraversalService` utilizing `NeptuneClient` and `CypherQueryLibrary`:
    - Disruption blast radius calculation (`get_disruption_blast_radius`): traverses supplier -> affected SKUs -> consuming assembly plants -> vehicle programs, resolving canonical NanoCore golden scenario (`SUP-NC-882` -> `CMP-MCU-X91` -> `PLT-MUC-01` -> `PRG-HGT-2026`).
    - Affected components resolution (`get_affected_components`): maps criticality, days of cover, daily consumption rate, and single-source flags.
    - Affected plants resolution (`get_affected_plants`): supports direct and BOM-based assembly plant traversal with financial downtime rates.
    - Multi-tier chain traversal (`get_tier_chain`): resolves paths from sub-tier suppliers (Tier-2/3) to Tier-1 direct OEM suppliers.
    - Single-source dependency detection (`find_single_source_risks`): identifies sole-supplier vulnerability components and single-source flags.
    - Geopolitical exposure resolution (`get_geopolitical_exposure`): correlates regional and geopolitical threats to supplier operations.
    - Ego-subgraph extraction (`get_supplier_subgraph`): compiles 2-hop deduplicated nodes and edges for frontend visualization (`GET /api/v1/suppliers/{id}/graph`).
    - Domain exception hierarchy: maps `NeptuneTimeoutError` to `TraversalError(status_code=504)` and connection/circuit-breaker failures to status 503.
    - Exported domain models and service in `src/graph/__init__.py`.
  - 15 comprehensive unit tests in `tests/unit/test_supplier_traversal.py` achieving **100% statement coverage** on `src/graph/traversal.py` (217 total passing tests across suite, 95% total coverage).
- **P5-5 · Graph Traversal Unit Tests (`feature/graph-traversal-tests`)**: Completed ✅
  - `src/graph/queries/library.py`: Added canonical `QUERY_FIVE_HOP_DISRUPTION_PATH` and registered `five_hop_disruption_path` query template in `CYPHER_QUERIES`.
  - `src/graph/traversal.py`: Implemented `DisruptionPath` dataclass, `get_five_hop_disruption_paths`, `is_single_source`, and `get_component_source_redundancy` on `SupplierTraversalService`.
  - `tests/unit/test_graph_traversal_paths.py`: Added 12 comprehensive unit tests asserting:
    - 5-hop path from NewsEvent (`EVT-NEWS-2026-081` -> `SUP-NC-882` -> `CMP-MCU-X91` -> `ASM-BECU-04` -> `PLT-MUC-01` -> `PRG-HGT-2026`).
    - 5-hop path from GeopoliticalRisk (`RISK-GEO-TW-01` -> `SUP-NC-882` -> `CMP-MCU-X91` -> `ASM-BECU-04` -> `PLT-MUC-01` -> `PRG-HGT-2026`).
    - 5-hop multi-tier supply chain path (`SUP-RAW-901` -> `SUP-NC-882` -> `CMP-MCU-X91` -> `ASM-BECU-04` -> `PLT-MUC-01` -> `PRG-HGT-2026`).
    - Exact 5-hop assertions: length=5, 6 distinct node entities, continuous causal lineage.
    - Single-source dependency detection: sole-supplier part identification, contractual flag validation, and multi-source redundancy exclusion (`CMP-PMIC-440` verified not flagged).
    - Query latency SLO compliance (<=2.0s per CLAUDE.md Sec 7) and timeout/circuit-breaker exception mapping (504, 503, 400).
    - Offline isolation: zero network or AWS calls using mock NeptuneClient.
  - Achieved **100% statement and branch coverage** on `src/graph/traversal.py` (259 statements) and `src/graph/queries/library.py` (47 statements).
  - Total passing unit tests: **229 passed** (95% project-wide test coverage).
  - **Phase 5 (Knowledge Graph — Amazon Neptune) is now 100% complete (5/5 tasks).**

### Phase 6: Kafka Event Ingestion
- **P6-1 · Kafka Consumer (`feature/kafka-event-consumer`)**: Completed ✅
  - `src/kafka/consumer.py`: Implemented robust MSK consumer group event ingestion service (`EventConsumer`):
    - At-least-once delivery semantics: disabled auto-commits (`enable_auto_commit=False`), enforcing explicit manual offset commits strictly after successful message handler completion or successful dead-letter queue persistence.
    - Transient fault recovery: automatic retry mechanism attempting up to 3 executions with exponential backoff on transient processing errors.
    - Forensic Dead-Letter Queue (DLQ): on 3 consecutive failures, publishes comprehensive forensic metadata payload (`original_topic`, `original_partition`, `original_offset`, `original_key`, `original_payload`, `error_message`, `failure_count`, `failed_at`, `trace_id`) to `<topic>.dlq` (`settings.KAFKA_TOPIC_SUPPLIER_EVENTS + ".dlq"`).
    - DLQ fault tolerance: offset is strictly NOT committed if DLQ publish fails, preventing data loss and preserving at-least-once delivery guarantees.
    - Resilient deserialization: parses valid JSON, gracefully retains string or raw binary payloads, and logs payload diagnostics.
    - Distributed trace context propagation: extracts `X-Trace-ID` / `trace_id` from message headers, binds trace context, and falls back to deterministic UUID generation.
    - Lifecycle management: provides non-blocking batch polling (`poll`), single-cycle batch runner (`run_once`), continuous loop with exception handling, and clean resource teardown (`close`).
    - Domain exception hierarchy: `KafkaConsumerError`, `KafkaDLQError`, and `KafkaMessageProcessingError` subclassing `AppException`.
    - Exported models and consumer in `src/kafka/__init__.py`.
  - 19 comprehensive unit tests in `tests/unit/test_kafka_consumer.py` achieving **99% statement coverage** on `src/kafka/consumer.py` (248 total passing tests across suite, 94.8% total coverage).
- **P6-2 · Kafka Producer (`feature/kafka-event-producer`)**: Completed ✅
  - `src/kafka/producer.py`: Implemented enterprise Kafka event publishing service (`EventProducer`):
    - At-least-once delivery guarantees: configured `acks="all"`, `retries=3`, `compression_type="gzip"`, and synchronous broker confirmation (`future.get(timeout)`).
    - Dedicated domain event dispatch methods:
      * `publish_risk_alert`: routes calculated risk alerts to `risk-alerts` topic, extracting partition keys from `supplier_id` / `alert_id` / `sku`.
      * `publish_hitl_request`: routes approval requests to `hitl-required` topic, extracting partition keys from `action_id` / `alert_id`.
      * `publish_audit_event`: routes forensic logs to `audit-events` topic, extracting partition keys from `entity_id` / `trace_id`.
    - Generic and batch publishing APIs supporting both synchronous (`publish`, `publish_batch`) and non-blocking asynchronous (`publish_async`, `publish_batch_async`) execution.
    - Precision-preserving serialization (`EventJSONEncoder`): serializes `Decimal` monetary values (BR-RULE-001) as high-precision strings, plus `datetime`, `date`, `UUID`, Pydantic models, and dataclasses without precision loss.
    - Distributed tracing and metadata enrichment (`format_headers`): automatically attaches `X-Trace-ID`, `X-Client-ID`, and `X-Timestamp` to all message headers.
    - Resilient error translation: maps Kafka timeout failures to `KafkaPublishTimeoutError` (504), broker disconnects to `KafkaBrokerUnavailableError` (503), and payload failures to `KafkaSerializationError` (400).
    - Lifecycle and context managers (`flush`, `close`, `__enter__`, `__exit__`, `__aenter__`, `__aexit__`).
    - Global thread-safe singleton accessor `get_event_producer()`.
    - Exported models, exceptions, and producer in `src/kafka/__init__.py`.
  - 30 comprehensive unit tests in `tests/unit/test_kafka_producer.py` achieving **100% statement and branch coverage** on `src/kafka/producer.py` (278 total passing tests across suite, 95.56% total coverage).
- **P6-3 · Event Schemas (`feature/kafka-event-schemas`)**: Completed ✅
  - `src/kafka/schemas/`: Implemented strict Pydantic v2 domain schemas for all 4 core Kafka topics:
    * `SupplierEvent` (`supplier-events`): Inbound disruption signals (`event_id`, `event_type`, `supplier_id`, `source`, `severity`, `description`, `affected_skus`, `metadata`).
    * `RiskAlert` / `RiskAlertEvent` (`risk-alerts`): Calculated risk assessments with `Decimal` inventory and monetary precision (`days_of_cover`, `gap_days`, `shortage_volume`, `financial_exposure`), severity thresholds, and automatic HITL derivation.
    * `HITLRequest` / `HITLRequestEvent` (`hitl-required`): Spend approval commitments (`action_id`, `amount_usd`, `spend_tier`, `required_signers_count`, `status`, `expires_at`), strictly enforcing spend tiers (`CATEGORY_MGR` <= $25k, `PROC_DIRECTOR` <= $100k, `DUAL_VP` > $100k) and dual executive signature count.
    * `AuditEvent` / `AuditEventSchema` (`audit-events`): Immutable forensic audit entries streaming to S3 WORM archive with automated recursive sanitization of credential keys (`token`, `password`, `kms_key`, `secret`).
  - Base architecture: `BaseEvent` enforces `extra="forbid"`, automatic whitespace stripping, UTC timestamp enforcement, distributed trace propagation, exact Decimal string serialization, and JSON schema registry export (`model_json_schema()`).
  - 29 comprehensive unit tests in `tests/unit/test_kafka_schemas.py` achieving **100% statement and branch coverage** on all schema modules (307 total passing tests across suite, 95.95% total coverage).
- **P6-4 · Consumer Integration Test (`feature/kafka-consumer-integration-test`)**: Completed ✅
  - `src/kafka/handlers.py`: Implemented robust Kafka topic consumer handler and persistence pipeline:
    * `persist_risk_alert`: Parses, validates, and persists `RiskAlert` event payloads to Aurora PostgreSQL `risk_alerts` table using `RiskAlertRepository`.
    * Idempotent redelivery guard: detects existing alerts by ID, performing atomic in-place updates rather than failing with primary key collision crashes (SEC-032).
    * Entity ID coercion: normalizes alert IDs to UUID (supporting standard UUID and deterministic UUIDv5 strings), and resolves business supplier identifiers (e.g. `SUP-NC-882`) to database `suppliers.id` foreign keys.
    * The Triad of Responsibility (BR-RULE-001): guarantees exact `Decimal` precision preservation for `days_of_cover`, `gap_days`, and `financial_exposure` with zero float truncation.
    * `create_risk_alert_consumer_handler`: Closure factory binding async session factories to `EventConsumer.register_handler()`.
  - Exported handler functions in `src/kafka/__init__.py`.
  - `tests/integration/test_kafka_consumer_integration.py`: Added 11 comprehensive integration tests asserting:
    * Publishing 3 canonical `RiskAlert` events via `EventProducer`, consuming via `EventConsumer`, and verifying all 3 persisted in `risk_alerts` table with exact Decimal numbers, status, and supplier foreign keys.
    * Strict manual offset commits executed only after successful database transaction commit.
    * Idempotent redelivery handling duplicate events without database violation.
    * Trace ID context propagation from Kafka message headers (`X-Trace-ID`) to logs and database records.
    * Corrupt / poisonous event routing to Dead-Letter Queue (`risk-alerts.dlq`) without database commit.
    * Batch publishing and sequential consumption.
    * Testcontainers environment detection preserving offline test isolation.
  - Achieved **100% statement and branch coverage** on `src/kafka/handlers.py` (80 statements) and **96.08%** project-wide test coverage across 318 passing tests.
  - **Phase 6 (Kafka Event Ingestion) is now 100% complete (4/4 tasks).**

### Phase 7: Deterministic Risk Engine
- **P7-1 · Risk Calculator (`feature/risk-calculator-core`)**: Completed ✅
  - `src/services/risk/calculator.py`: Implemented 100% deterministic supply chain risk calculation engine adhering strictly to The Triad of Responsibility (BR-RULE-001):
    * **Zero LLM Math**: Pure Python arithmetic with zero probabilistic inference or floating-point drift.
    * **Strict Decimal Precision**: Enforced `Decimal` with `ROUND_HALF_UP` rounding across all calculations (`days_of_cover`, `gap_days`, `shortage_volume`, `financial_exposure`, `factory_halt_exposure`).
    * **Canonical NanoCore Golden Scenario**: Reproduces exact reference values to the cent:
      - Days of Cover: `142,000 / 18,500 = 7.68` days
      - Shortage Gap: `9.00 - 7.68 = 1.32` days
      - Shortage Volume: `1.32 * 18,500 = 24,420` units
      - Financial Exposure: `24,420 * $100.25 = $2,448,105.00`
    * **Factory Line Halt Exposure**: Calculated downtime hours (`gap_days * operating_hours_per_day`) multiplied by hourly factory halt rate (e.g. €85,000/hr -> €2,692,800.00).
    * **Comprehensive Edge Case Guards**:
      - Zero inventory stock (`current_stock = 0`) -> `days_of_cover = 0.00`, full ETA gap.
      - Zero consumption rate (`daily_consumption_rate = 0`) -> capped at `999.00` days (`DAYS_OF_COVER_MAX_CAP`), `gap = 0.00`, `shortage = 0`.
      - Negative gap (healthy inventory buffer where ETA < days of cover) -> strictly clamped to `0.00` gap, `0` shortage volume, `$0.00` exposure.
      - Exact zero gap (just-in-time replenishment) -> `0.00` gap.
      - Zero unit cost -> `$0.00` exposure.
      - Negative inputs (stock < 0, rate < 0, ETA < 0, cost < 0) -> raises `InvalidInventoryInputError`.
    * **Cryptographic Verification**: Computes deterministic SHA-256 verification hash across all input and output parameters.
  - Exported classes and exceptions in `src/services/risk/__init__.py` and `src/services/__init__.py`.
  - 19 comprehensive unit tests in `tests/unit/test_risk_calculator.py` achieving **100% statement and branch coverage** on `src/services/risk/calculator.py` (139 statements) and **96.28%** total project coverage across 337 passing tests.
- **P7-2 · Risk Scorer (`feature/risk-scorer`)**: Completed ✅
  - `src/services/risk/scorer.py`: Implemented 100% deterministic supply chain risk classification engine adhering strictly to The Triad of Responsibility (BR-RULE-001) and `CLAUDE.md:428-439`:
    * **Zero LLM Thresholds**: Severity classification operates exclusively via pure Python arithmetic without probabilistic drift or LLM hallucination.
    * **Strict Decimal Comparisons**: Evaluates coverage gap and financial exposure against exact `Decimal` threshold boundaries:
      - `CRITICAL`: `gap > 0` AND `financial_exposure > $1,000,000.00`
      - `HIGH`: `gap > 0` AND `financial_exposure > $250,000.00` (up to `$1,000,000.00`)
      - `MEDIUM`: `gap > 0` (exposure <= `$250,000.00`) OR `supplier_risk_score > 0.70`
      - `LOW`: `gap <= 0` AND `supplier_risk_score <= 0.70`
    * **Canonical NanoCore Reference Scenario**:
      - Inputs: `days_of_cover = 7.68`, `eta_days = 9.00` (`gap = 1.32`), `financial_exposure = $2,448,105.00`, `supplier_risk_score = 0.885`.
      - Output: Assigns `RiskLevel.CRITICAL`, `is_single_source = True`, requires HITL with `SpendTier.DUAL_VP`.
    * **HITL Spend Governance Routing**: Integrates with `SpendTier` / `SpendTierRouter`:
      - Spend <= $25,000: Category Manager approval (1-hr TTL, `SpendTier.CATEGORY_MGR`).
      - Spend $25,001 - $100,000: Procurement Director approval (1-hr TTL, `SpendTier.PROC_DIRECTOR`).
      - Spend > $100,000: Dual sign-off (30-min TTL, `SpendTier.DUAL_VP`).
      - Non-zero exposure and CRITICAL/HIGH alerts unconditionally mandate human authorization.
    * **Frozen Data Model & JSON Serialization**: `RiskScoreResult` preserves numeric precision with string `Decimal` serialization in `to_dict()`.
    * **Strict Input Validation**: Rejects negative inventory metrics, negative exposure, and out-of-range supplier risk scores (`[0.0, 1.0]`) via `InvalidRiskScoringInputError` (HTTP 400).
  - Exported classes, functions, and threshold constants in `src/services/risk/__init__.py` and `src/services/__init__.py`.
  - 14 comprehensive unit tests in `tests/unit/test_risk_scorer.py` achieving **100% statement and branch coverage** on `src/services/risk/scorer.py` (110 statements) and **96.42%** total project coverage across 351 passing tests.
- **P7-3 · Inventory Aggregation Service (`feature/risk-inventory-service`)**: Completed ✅
  - `src/services/risk/inventory_service.py`: Implemented deterministic inventory aggregation service pulling real-time stock balances, burn rates, and replenishment metrics from Aurora PostgreSQL with Redis caching.
    * **The Triad of Responsibility (BR-RULE-001)**: 100% deterministic pure Python math and data aggregation with zero LLM math or probabilistic hallucination.
    * **Layered Read-Through Caching**: Checks Redis cache first with 30-minute default TTL (`DEFAULT_CACHE_TTL_SECONDS = 1800` per LLD Section 6.1: `CACHE_TTL: 30m`), returning cached records with `data_source="REDIS_CACHE"` and `is_cached=True`.
    * **Cache Invalidation & Write-Through**: Explicit cache purge on stock updates, plant invalidation, and `force_refresh=True` bypass.
    * **Dual Fault-Tolerant Circuit Breaker**:
      - Redis connection outage / network partition transparently degrades to Aurora database queries without crashing the pipeline.
      - Aurora database partition degrades to Redis cached balance (LLD Section 6.1 circuit breaker fallback: `Load cached inventory balance from Redis`).
    * **Multi-Plant Stock Aggregation**: `PlantInventoryAggregate` combines usable stock, daily burn, and safety buffers across Munich (`PLT-MUC-01`), Bengaluru (`PLT-BLR-01`), and Pune (`PLT-PUN-01`), computing composite days of cover.
    * **Physical Inventory Constraints**: Prevents negative inventory underflow mutations (`current_stock + delta < 0`) via `InvalidInventoryOperationError` (HTTP 400).
    * **Risk Assessment Bridge**: `assess_component_risk()` seamlessly bridges inventory records to `RiskCalculator`, reproducing exact NanoCore metrics (7.68 days cover, 1.32 days gap, $2,448,105.00 exposure).
  - `src/database/models.py`: Declared `InventorySnapshot` model mapping to `inventory_snapshots` table in Aurora with check constraints on non-negative stock, consumption, and cost.
  - `src/database/repositories/inventory_repository.py`: Implemented async `InventoryRepository` providing CRUD, plant queries, and stock mutation operations with 100% statement coverage.
  - Exported classes and exceptions in `src/database/__init__.py`, `src/services/risk/__init__.py`, and `src/services/__init__.py`.
  - 25 comprehensive unit tests in `tests/unit/test_inventory_service.py` achieving **100% coverage** on `src/database/repositories/inventory_repository.py` and **92% coverage** on `src/services/risk/inventory_service.py`, bringing total passing test suite to 376 tests.
- **P7-4 · Alert Deduplication (`feature/risk-alert-deduplication`)**: Completed ✅
  - `src/services/alert_service.py`: Implemented deterministic alert deduplication service collapsing identical supplier and component disruption events within a rolling 1-hour window (`DEFAULT_DEDUPLICATION_WINDOW_SECONDS = 3600`):
    * **The Triad of Responsibility (BR-RULE-001)**: 100% pure deterministic Python logic for window evaluation, metric comparisons, and deduplication actions. Zero LLMs.
    * **Rolling Deduplication Window**: Identical signals for `(supplier_id, component_sku)` arriving within 1 hour collapse into a single master alert record (`AlertAction.COLLAPSED`), preventing alert storming and redundant database entries (`SEC-036`).
    * **Severity Escalation & Metric Preservation**: If a duplicate signal arrives with worse metrics (higher severity level `CRITICAL > HIGH > MEDIUM > LOW`, higher financial exposure, lower days of cover, or larger shortage volume), the master alert escalates (`AlertAction.ESCALATED`). Milder incoming signals retain existing worst-case metrics.
    * **Layered Redis Deduplication**: Employs fast-path key lookup (`alert:dedup:<supplier_id>:<component_sku>`) with 1-hour TTL. Catches Redis exceptions gracefully and falls back to Aurora repository query scan (`find_recent_active_alert`), guaranteeing continuous operation during cache outages.
    * **Terminal Status Cache Eviction**: Moving alerts to terminal states (`CLOSED`, `RESOLVED`, `DISMISSED`) immediately evicts the Redis deduplication key, allowing fresh subsequent disruption signals to create new active alerts.
    * **NanoCore Canonical Golden Verification**: 3 successive disruption signals (News cleanroom fire at T=0m, Plant MES buffer warning at T=15m, Logistics shipment delay at T=40m) collapse to exactly 1 master alert in Aurora with `$2,448,105.00` financial exposure, `7.68` days cover, and `24,420` units shortage.
  - `src/database/repositories/risk_alert_repository.py`: Added `find_recent_active_alert(component_sku, supplier_id, window_seconds, reference_time)` with 96% coverage.
  - Exported `AlertService`, `AlertCreateInput`, `AlertAction`, `AlertDeduplicationResult`, `AlertServiceError`, `InvalidAlertOperationError` in `src/services/__init__.py`.
  - 21 comprehensive unit tests in `tests/unit/test_alert_service.py` achieving **100% statement and branch coverage** on `src/services/alert_service.py` (201 statements), bringing total passing test suite to 397 tests (96.31% project-wide coverage).
- **P7-5 · NanoCore Golden Tests (`feature/risk-nanocore-golden-tests`)**: Completed ✅
  - `tests/golden/test_nanocore_golden.py`: Implemented canonical golden dataset test suite mandated by CLAUDE.md Section 14 and GEMINI.md Section 2:
    * **Direct Golden File Assertions (`tests/golden/nanocore_scenario.json`)**:
      - Days of Cover: `7.68` days (`142,000 / 18,500 = 7.6756... -> 7.68`)
      - Coverage Gap: `1.32` days (`9.00 - 7.68 = 1.32`)
      - Shortage Volume: `24,420` units (`1.32 * 18,500 = 24,420`)
      - Direct Financial Exposure: `$2,448,105.00` (`24,420 * $100.25 = $2,448,105.00`)
      - Factory Line Halt Exposure: `€2,692,800.00` (`1.32 days * 24 hrs * €85,000.00/hr = €2,692,800.00`)
      - Total Financial Exposure: `$5,140,905.00` (`$2,448,105.00 + €2,692,800.00`)
      - Risk Severity Level: `CRITICAL`
      - HITL Spend Governance: `DUAL_VP` (2 distinct signatures, 30-min TTL)
    * **The Triad of Responsibility (BR-RULE-001)**: 100% pure deterministic Python arithmetic; zero float drift; exact `Decimal` precision with `ROUND_HALF_UP` rounding.
    * **Cryptographic Hash Reproducibility**: SHA-256 calculation hash is bit-for-bit reproducible across identical executions and sensitive to single-unit deviations.
    * **Deviation Resistance Guard**: Any rounding or calculation deviation strictly triggers build assertion failure (`CLAUDE.md:733`).
  - 8 comprehensive golden tests in `tests/golden/test_nanocore_golden.py` passing in 0.49s, bringing total test suite to 405 tests (96.31% project-wide coverage).
  - **Phase 7 (Deterministic Risk Engine) is now 100% complete (5/5 tasks).**

### Phase 8: LLM Foundation (LiteLLM Gateway & Guardrails)
- **P8-1 · LiteLLM Gateway Client (`feature/llm-litellm-gateway`)**: Completed ✅
  - `src/llm/gateway.py`: Implemented unified LiteLLM gateway client routing completions to Amazon Bedrock Anthropic models with automated resilience, fallback, and cost metering:
    * **Model Routing by Task Complexity**:
      - `TaskType.SYNTHESIS` & `TaskType.GENERAL` route to Claude 3.5 Sonnet (`anthropic.claude-3-5-sonnet-20241022-v2:0`).
      - `TaskType.TRIAGE` & `TaskType.EXTRACTION` route to Claude 3.5 Haiku (`anthropic.claude-3-5-haiku-20241022-v1:0`).
    * **Automated Fallback & Resilience**: Transparently catches transient 429 RateLimit, 503 ServiceUnavailable, and 504 Timeout errors from the primary model and retries via the secondary model (e.g., Sonnet -> Haiku) with `is_fallback=True` without breaking caller flows.
    * **Error Standardization**: Translates raw vendor exceptions into standard domain exceptions (`LLMRateLimitError`, `LLMTimeoutError`, `LLMServiceUnavailableError`, `LLMContextWindowExceededError`, `LLMGatewayError`).
    * **Strict Decimal Token Cost Tracking (BR-RULE-001)**: Computes input, output, and total costs using exact `Decimal` precision quantized to `$0.000001` (micro-dollar precision) based on Bedrock rates ($3.00/$15.00 per 1M tokens for Sonnet; $0.80/$4.00 per 1M tokens for Haiku). Thread-safe cumulative ledger tracking via `get_cost_report()` and `reset_cost_tracking()`.
    * **Offline Mock Execution**: Zero external network dependency when `use_mock=True` or `USE_MOCK_LLM=true`, enabling fast, deterministic offline testing.
    * **In-Memory Semantic Caching**: SHA-256 prompt hashing for hit/miss caching with configurable bypass.
    * **Distributed Trace Propagation**: Propagates context `trace_id` to response metadata.
  - `src/llm/__init__.py`: Package exports for `LiteLLMGateway`, `LLMResponse`, `CostReport`, `TaskType`, `calculate_token_cost`, `get_litellm_gateway`, and exception classes.
  - 19 comprehensive unit tests in `tests/unit/test_litellm_gateway.py` achieving **100% statement and branch coverage** on `src/llm/gateway.py` (235 statements), bringing total test suite to 424 tests (96.55% project-wide coverage).
- **P8-2 · Quarantined Reader (`feature/llm-quarantined-reader`)**: Completed ✅
  - `src/llm/quarantined_reader.py`: Implemented prompt injection defense, tag stripping, token budget enforcement, and passive XML structural encapsulation for all untrusted external text:
    * **Layering Invariants (CLAUDE.md Sec 5.2 & 8.1)**: Ensures no raw external text (contracts, news, SEC filings, supplier emails) ever reaches an LLM without passing through `QuarantinedReader.sanitize()`.
    * **Tag & Control Character Sanitization**: Strips non-printable ASCII characters (`[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\x7F]`), unescapes HTML entities, and strips script blocks, style definitions, and XML tags.
    * **Tag-Breakout Defense**: Strips delimiter breakout tags (`</untrusted_supplier_data>`, `<untrusted_signal>`, `<system>`, `<instructions>`), preventing prompt escape attacks.
    * **Adversarial Directive Detection & Redaction**: Flags high-risk injection sequences (`ignore prior instructions`, `disregard prompt`, `system override`, `DAN mode`, `jailbreak`, `drop table`, `reveal system prompt`), calculates `injection_score` in `[0.0, 1.0]`, sets `is_safe=False` when score $\ge 0.40$, and redacts directives with `[REDACTED_ADVERSARIAL_DIRECTIVE]`.
    * **Max Token Budget Enforcement**: Enforces token limit (default 8000 tokens) using `litellm.utils.token_counter` with binary search character cut and explicit truncation marker `[TRUNCATED: Exceeded max token budget of {max_tokens} tokens]`.
    * **Cryptographic Content Hashing**: Emits deterministic SHA-256 hashes for both raw and sanitized payloads.
    * **Passive XML Structural Encapsulation**: Encapsulates content in `<untrusted_supplier_data source="{source_id}" safe="{is_safe}" hash="{hash}">`.
    * **Autonomous Forensic Audit Logging (BR-RULE-007)**: `sanitize_async()` writes immutable records to `audit_logs` via `write_audit_log` with graceful degradation on database outages unless `strict_audit=True`.
    * **Multi-Document Evidence Extraction**: `extract(documents)` processes lists of strings or dicts, returning concatenated quarantined sections for agent synthesis prompts.
  - `src/llm/__init__.py`: Package exports for `QuarantinedReader`, `SanitizedPayload`, `PromptInjectionDetectedError`, `quarantined_reader`, `get_quarantined_reader`, and `sanitize`.
  - 29 comprehensive unit tests in `tests/unit/test_quarantined_reader.py` achieving **100% statement and branch coverage** on `src/llm/quarantined_reader.py` (131 statements), bringing total test suite to 453 tests (96.67% project-wide coverage).
- **P8-3 · Pydantic Output Schemas (`feature/llm-pydantic-output-schemas`)**: Completed ✅
  - `src/llm/models.py`: Engineered strongly-typed Pydantic v2 output schemas enforcing structured outputs across all agent nodes and rejecting unstructured free text:
    * **Layering Invariants (CLAUDE.md Sec 5.2 & Sec 20.4)**: Every LLM completion strictly produces a validated Pydantic model (`Citation`, `ResearchAnalysis`, `ContractAnalysis`, `RiskNarrative`, `MitigationScenario`, `RecommendationReport`, `IncidentCaseDossier`). Free-text responses are strictly rejected.
    * **Prompt Injection Defense (`extra='forbid'`)**: All models forbid extra attributes, preventing malicious prompt injection payloads from mutating schema boundaries or injecting unvalidated control fields.
    * **The Triad of Responsibility (BR-RULE-001)**: Mathematical calculations are decoupled from LLMs. All financial values (costs, avoided losses, net benefits, liability caps, penalty rates) strictly enforce exact `Decimal` precision with zero floating-point drift.
    * **Arithmetic Consistency Enforcement**: `MitigationScenario` validates that `net_financial_benefit_usd == avoided_loss_usd - estimated_cost_usd`.
    * **Mandatory Human-in-the-Loop Gating**: `RecommendationReport` enforces that any scenario with financial spend (`estimated_cost_usd > 0`) cannot bypass human authorization (`requires_hitl=True`), and validates that `recommended_scenario_id` exists in the scenario list.
    * **Structured Output Parsing Pipeline**: `parse_structured_llm_response()` safely strips markdown code fences (` ```json ... ``` `), parses JSON, validates against the target Pydantic model, and raises RFC 7807 compatible `StructuredOutputParsingError` (HTTP 422 `ERR_422_UNSTRUCTURED_OUTPUT`) on invalid free text.
  - `src/llm/__init__.py`: Package exports for all models, enums, exception classes, and parsing utilities.
  - 22 comprehensive unit tests in `tests/unit/test_llm_models.py` achieving **100% statement and branch coverage** on `src/llm/models.py` (172 statements), bringing total test suite to 475 tests (96.81% project-wide coverage).
- **P8-4 · vLLM Confidential Contract Client (`feature/llm-vllm-contract-client`)**: Completed ✅
  - `src/llm/vllm_client.py`: Implemented self-hosted vLLM confidential contract client (`VLLMClient`) and data sovereignty router (`ConfidentialContractRouter`) enforcing strict isolation of proprietary agreements:
    * **Data Sovereignty Enforcement (NFR-SEC-02, CLAUDE.md Sec 5.2, GAP-002)**: Directs EU-regulated agreements (32 EU/EEA member states), GDPR-governed agreements, and contracts classified as `CONFIDENTIAL`, `HIGHLY_CONFIDENTIAL`, or `RESTRICTED` exclusively to the private VPC self-hosted vLLM GPU cluster (`settings.VLLM_BASE_URL="http://localhost:8080"`, `VLLM_MODEL="meta-llama/Llama-3.1-70B-Instruct"`).
    * **Mandatory Data Sovereignty Guardrail**: Implemented strict security gate (`VLLMDataSovereigntyViolationError`, HTTP 403 `DATA_SOVEREIGNTY_VIOLATION`) unconditionally blocking any attempt to route or force sovereign contracts to external third-party multi-tenant model providers (such as Amazon Bedrock Claude).
    * **OpenAI-Compatible vLLM Protocol**: Interfaces with `/v1/chat/completions` enforcing `response_format={"type": "json_object"}`, distributed `X-Trace-ID` propagation, and exponential retry backoff on transient cluster timeouts (HTTP 504 `VLLMTimeoutError`) and network outages (HTTP 503 `VLLMConnectionError`).
    * **Cryptographic SHA-256 Audit Trail & Privacy Shield (BR-RULE-007)**: Computes deterministic SHA-256 contract hashes for immutable audit logging while strictly guaranteeing raw proprietary contract text is never logged unencrypted to standard output or logs.
    * **Strict Decimal Precision Invariant (BR-RULE-001)**: Daily delay penalties, liability ceilings, and commercial terms strictly enforce `Decimal` precision with zero floating-point conversion.
    * **Deterministic Offline Isolation (USE_MOCK_LLM=true)**: Produces deterministic schema-compliant `ContractAnalysis` payloads adhering to P8-3 models without external network or GPU cluster I/O.
  - `src/core/config.py`: Added `VLLM_MODEL` and `VLLM_API_KEY` configuration settings.
  - `src/llm/__init__.py`: Package exports for `VLLMClient`, `ConfidentialContractRouter`, `ContractMetadata`, `ContractClassification`, `EU_EEA_JURISDICTIONS`, exception classes, and dependency-injection singletons.
  - 36 comprehensive unit tests in `tests/unit/test_vllm_client.py` achieving **100% statement and branch coverage** on `src/llm/vllm_client.py` (223 statements), bringing total test suite to 511 tests (96.98% project-wide coverage).
  - PR #38 merged into `development`.
- **P8-5 · Mock LLM Client & Schema Fixture Engine (`feature/llm-mock-client-fixtures`)**: Completed ✅
  - `src/llm/fixtures/`: Created canonical JSON fixtures strictly validating against P8-3 Pydantic schemas:
    * `research_analysis.json`: NanoCore semiconductor cleanroom fire, 9-day disruption, 94% confidence.
    * `contract_analysis.json`: Master supply agreement, Net 30, 14 days notice, 0.02% delay penalty, $5M liability cap.
    * `risk_narrative.json`: Executive commentary, runway analysis, 7.68 days cover, 1.32 days shortage gap, $2,448,105 financial exposure.
    * `recommendation_report.json`: Multi-scenario mitigation (spot buy + air freight vs. line re-allocation), dual VP sign-off gate ($285k commit).
    * `incident_case_dossier.json`: Comprehensive forensic dossier consolidating research, contract, narrative, metrics, and recommendations.
    * `src/llm/fixtures/__init__.py`: Fixtures directory path resolver (`FIXTURES_DIR`).
  - `src/llm/mock_client.py`: Implemented `MockLLMClient` and fixture loading engine:
    * **Deterministic Fixture Loader**: `load_fixture_json()` and `get_fixture_model()` parsing canonical JSON fixtures into validated Pydantic models.
    * **Intelligent Schema Inference**: Contextually infers target schema (`ResearchAnalysis`, `ContractAnalysis`, `RiskNarrative`, `RecommendationReport`, `IncidentCaseDossier`) from domain keywords in prompt text when not explicitly provided.
    * **FIFO Response Queue & Dynamic Overrides**: Thread-safe FIFO response queue (`enqueue_response`, `enqueue_responses`, `clear_queue`) and per-schema fixture overrides (`set_fixture`, `reset_fixtures`) for customized agent tests.
    * **LiteLLMGateway Integration**: Integrated with `LiteLLMGateway.acomplete(response_model=...)`, delegating structured mock completions to `MockLLMClient` when `USE_MOCK_LLM=true` or `use_mock=True`.
    * **Simulated Metrics & Telemetry**: Emits zero-cost `Decimal("0.000000")`, simulated token counts, simulated latency, active `trace_id`, and rich metadata.
    * **Thread-Safe Dependency Injection**: Singleton accessor `get_mock_llm_client()`.
  - `src/llm/__init__.py`: Exported all mock client, schema mapping, and fixture loader symbols.
  - 22 comprehensive unit tests in `tests/unit/test_mock_llm_client.py` achieving **100% statement and branch coverage** on `src/llm/mock_client.py` (137 statements), bringing total test suite to 533 tests (97.09% project-wide coverage).
  - PR #39 merged into `development`.

### Phase 9: Multi-Agent System (LangGraph Orchestration)
- **P9-1 · LangGraph AgentState and StateGraph Skeleton (`feature/agents-langgraph-skeleton`)**: Completed ✅
  - `src/agents/state.py`: Formulated `SupplierRiskState` and `AgentState` schema using `TypedDict` with `operator.add` reducers on additive channels (`execution_path`, `errors`, `audit_events`, `evidence`). Explicitly decoupled quantitative metrics (`risk_metrics`) from qualitative narrative (`narrative`).
  - `src/agents/graph.py`: Implemented deterministic directed acyclic graph (DAG) in LangGraph with node stubs (`triage`, `research`, `contract`, `risk`, `recommendation`, `hitl_gate`, `action`, `dismiss`) and conditional routing functions (`route_after_triage`, `route_after_risk`, `route_after_hitl_gate`).
    * **The Triad of Responsibility (BR-RULE-001)**: Mathematical computations strictly invoke deterministic Python microservices (`RiskCalculator().calculate()`). LLMs never perform math.
    * **HITL Spend Gate**: Consequential spend actions are conditionally halted at `hitl_gate`, transitioning to `AWAITING_APPROVAL` unless verified cryptographic tokens are present.
  - `src/agents/orchestrator.py`: Implemented `InvestigationOrchestrator` lifecycle runner supporting stateful checkpointing via `MemorySaver` / `AsyncPostgresSaver`, suspension at HITL gates, and clean resumption upon human sign-off.
  - `src/agents/__init__.py`: Package exports for state models, node constants, routing functions, and orchestrator.
  - 17 unit tests in `tests/unit/test_agent_graph_skeleton.py` achieving **100% statement and branch coverage** on `src/agents/` (247 statements), bringing total test suite to 550 tests (97.24% project-wide coverage).
- **P9-2 · Triage Agent Node (`feature/agents-triage-node`)**: Completed ✅
  - `src/agents/nodes/triage_agent.py`: Implemented deterministic signal classifier (`TriageAgent`), immutable classification container (`TriageResult`), singleton factory (`get_triage_agent()`), and LangGraph node entrypoint (`triage_node()`):
    * **100% Deterministic Rule & Keyword Engine (BR-RULE-001)**: Zero LLM math and zero LLM classification. Categorizes incoming disruption signals into news, financial, logistics, and geopolitical taxonomies with bounded confidence scoring (0.80 to 0.98).
    * **Prompt Injection Defense & Quarantine (CLAUDE.md Sec 8.1 & LLD Sec 5.2)**: All untrusted text is pre-sanitized via `QuarantinedReader`, stripping control characters, script blocks, HTML/XML tags, and neutralizing delimiter breakout attacks prior to state propagation.
    * **Early Zero-Impact Blast Radius Detection**: Automated early detection of benign or pre-cleared signals (via metadata or regex indicators), transitioning workflow to `DISMISSED` and routing directly to `NODE_DISMISS` without consuming LLM budget.
    * **Composite Disruption Fan-Out Routing**: Multi-faceted disruptions (e.g., bankruptcy + fab fire) dynamically fan out to both `NODE_RESEARCH` and `NODE_CONTRACT` in parallel branches before converging into `NODE_RISK`.
    * **Immutable Audit Trail Recording**: Records `SIGNAL_TRIAGED` events with detected signal type, confidence score, and target nodes into `audit_events` reducer channel.
  - `src/agents/nodes/__init__.py`: Package exports for `triage_node`, `TriageAgent`, `TriageResult`, `get_triage_agent`, and node constants.
  - `src/agents/graph.py`: Connected real `triage_node` and updated `route_after_triage` to honor metadata `is_zero_impact` and pre-computed `target_nodes`.
  - 15 unit tests in `tests/unit/test_triage_agent.py` achieving **100% statement and branch coverage** on `src/agents/nodes/triage_agent.py` (112 statements), bringing total test suite to 565 tests (97.31% project-wide coverage).
- **P9-3 · Research Agent Node (`feature/agents-research-node`)**: Completed ✅
  - `src/agents/tools/research_tools.py`: Implemented specialized intelligence research tools with mandatory QuarantinedReader sanitization:
    * **NewsScraperTool**: Searches external news articles and industry feeds, retrieving canonical NanoCore fab fire intelligence, trans-Pacific freight bottlenecks, and general disruption alerts.
    * **SECEDGARTool**: Searches SEC EDGAR regulatory filings, retrieving material Form 8-K event disclosures (Item 2.01) and operational delay notices.
    * **GeopoliticalAPITool**: Evaluates regional trade sanctions, export controls, and supply chain concentration risks (e.g. Taiwan Strait / East Asia corridor).
    * **Mandatory Input Quarantine (CLAUDE.md Sec 8.1)**: Every tool output is strictly pre-sanitized via `QuarantinedReader`, stripping script blocks, HTML tags, ASCII control characters, and wrapping in `<untrusted_supplier_data>`.
  - `src/agents/tools/__init__.py`: Exported all research tools, data models (`ScrapedNewsItem`, `SECDiscloseItem`, `GeopoliticalRiskItem`), and singleton accessors.
  - `src/agents/nodes/research_agent.py`: Implemented `ResearchAgent`, `get_research_agent()`, and `research_node()`:
    * Coordinates tools, extracts verifiable `EvidenceItem` records into state with source provenance and confidence.
    * Synthesizes structured `ResearchAnalysis` via LiteLLM gateway (`response_model=ResearchAnalysis`), enforcing zero free-text responses (P8-3).
    * Implemented robust deterministic fallback synthesis on LLM degradation, ensuring the investigation pipeline never halts or crashes.
  - `src/agents/nodes/__init__.py` & `src/agents/graph.py`: Wired real `research_node` into the StateGraph DAG.
  - 12 unit tests in `tests/unit/test_research_agent.py` achieving **100% statement and branch coverage** across `research_agent.py` and `research_tools.py` (213 statements), bringing total test suite to 577 tests (97.43% project-wide coverage).
- **P9-4 · Contract Agent Node (`feature/agents-contract-node`)**: Completed ✅
  - `src/agents/nodes/contract_agent.py`: Implemented specialist contract intelligence agent (`ContractAgent`), singleton factory (`get_contract_agent()`), and LangGraph node entrypoint (`contract_node()`):
    * **Data Sovereignty Enforcement (NFR-SEC-02, CLAUDE.md Sec 5.2)**: Integrates `ConfidentialContractRouter` ensuring EU-regulated agreements (32 member states), GDPR-governed agreements, and contracts classified as `CONFIDENTIAL`, `HIGHLY_CONFIDENTIAL`, or `RESTRICTED` route strictly to private self-hosted vLLM GPU clusters inside the VPC. Attempting to route sovereign contracts to external Bedrock raises `VLLMDataSovereigntyViolationError` (HTTP 403 `DATA_SOVEREIGNTY_VIOLATION`).
    * **Untrusted Input Quarantine (CLAUDE.md Sec 8.1)**: Enforces mandatory pre-exposure quarantine via `QuarantinedReader.sanitize()` on all raw contract text and riders, stripping XML/HTML script tags, control characters, and computing SHA-256 hashes for audit log tracking.
    * **Structured Output Validation (P8-3)**: Emits typed Pydantic `ContractAnalysis` models with exact `Decimal` precision for daily delay penalties and liability caps (BR-RULE-001).
    * **Representative Contract Text Resolution**: Provides high-fidelity contract clauses for known suppliers (NanoCore Net 30, 0.02% delay penalty, Section 15.2 force majeure fire clause, $5M cap; BetaElectro EU-governed agreement with €2.5M cap) and custom contract text in state metadata.
    * **Resilient Deterministic Fallback Synthesis**: Automatically recovers with deterministic `ContractAnalysis` if the vLLM cluster encounters network outages or 5xx failures, ensuring continuous LangGraph pipeline operation.
    * **LangGraph State Machine Integration**: Emits state transitions conforming to `SupplierRiskState` (`current_node="contract"`, `workflow_status=WorkflowStatus.ANALYZING_CONTRACTS`, `contract_analysis`, `evidence`, `audit_events`).
  - `src/agents/nodes/__init__.py`: Package exports for `ContractAgent`, `get_contract_agent`, `contract_node`, and `NODE_CONTRACT`.
  - `src/agents/graph.py`: Replaced `contract_node` stub with production implementation, connecting real contract extraction into the StateGraph DAG.
  - 12 unit tests in `tests/unit/test_contract_agent.py` achieving **100% statement and 100% branch coverage** on `src/agents/nodes/contract_agent.py` (83 statements), bringing total test suite to 589 tests (97.47% project-wide coverage).
- **P9-5 · Risk Agent Node (`feature/agents-risk-node`)**: Completed ✅
  - `src/agents/nodes/risk_agent.py`: Implemented specialist risk intelligence agent (`RiskAgent`), singleton factory (`get_risk_agent()`), and LangGraph node entrypoint (`risk_node()`):
    * **The Triad of Responsibility (BR-RULE-001)**: 100% of arithmetic calculations (Days of Cover, Coverage Gap, Shortage Volume, Direct Financial Exposure, Factory Line Halt Exposure, Total Exposure) are performed strictly by deterministic microservices (`RiskCalculator` and `RiskScorer`). LLMs are strictly forbidden from executing arithmetic.
    * **Strict Decimal Precision Invariant**: All inventory and monetary calculations preserve exact `Decimal` precision (`ROUND_HALF_UP`, 2 decimal places), eliminating floating-point drift and reproducing the canonical NanoCore Golden Scenario with bit-for-bit exactness (`days_of_cover=7.68`, `gap_days=1.32`, `shortage_volume=24420`, `financial_exposure=$2,448,105.00`, `factory_halt_exposure=€2,692,800.00`, `total_exposure=$5,140,905.00`, `severity=CRITICAL`).
    * **Pydantic Structured Output Validation (P8-3)**: Synthesizes qualitative executive narrative explaining the deterministic numbers via LiteLLM gateway (`task_type=TaskType.SYNTHESIS`, Claude 3.5 Sonnet) enforcing `RiskNarrative` schema (`executive_summary`, `root_cause_analysis`, `operational_impact`, `runway_and_exposure_commentary`, and grounding `citations`).
    * **Resilient Deterministic Fallback Synthesis**: Automatically recovers with deterministic, grounded `RiskNarrative` on LLM timeouts or service disruptions, ensuring zero pipeline halts.
    * **LangGraph State Machine Integration**: Emits state transitions conforming to `SupplierRiskState` (`current_node="risk"`, `workflow_status=WorkflowStatus.CALCULATING_RISK`, `risk_metrics`, `severity`, `narrative`, `risk_narrative`, `evidence`, `audit_events`).
  - `src/agents/nodes/__init__.py`: Package exports for `RiskAgent`, `get_risk_agent`, `risk_node`, and `NODE_RISK`.
  - `src/agents/graph.py`: Replaced `risk_node` stub with production implementation, connecting real deterministic calculations and narrative synthesis into the StateGraph DAG.
  - 17 unit tests in `tests/unit/test_risk_agent.py` achieving **100% statement and 100% branch coverage** on `src/agents/nodes/risk_agent.py` (137 statements, 40 branches), bringing total test suite to 606 tests (97.53% project-wide coverage).
- **P9-6 · Recommendation Agent Node (`feature/agents-recommendation-node`)**: Completed ✅
  - `src/agents/nodes/recommendation_agent.py`: Implemented specialist recommendation agent (`RecommendationAgent`), singleton factory (`get_recommendation_agent()`), and LangGraph node entrypoint (`recommendation_node()`):
    * **Human-in-the-Loop Spend Tiers (BR-RULE-001)**: Any mitigation option involving financial expenditure (`estimated_cost_usd > $0.00`) mandates human authorization (`requires_hitl=True`) and deterministically resolves the governing spend tier (`get_spend_tier()`: Category Manager <= $25k, Procurement Director <= $100k, Dual VP > $100k).
    * **The Triad of Responsibility**: Probabilistic AI proposes and ranks alternative mitigation scenarios, but is strictly prohibited from executing capital dispatch or bypassing spend gates. Workflows pause at `hitl_gate` in `WorkflowStatus.AWAITING_APPROVAL` status when human approval is required.
    * **Strict Decimal Arithmetic Invariant**: All mitigation financial attributes preserve exact `Decimal` precision (`ROUND_HALF_UP`, 2 decimal places), enforcing `net_financial_benefit_usd == avoided_loss_usd - estimated_cost_usd` with zero float conversion.
    * **Structured Output Validation (P8-3)**: Synthesizes `RecommendationReport` via LiteLLM gateway (`task_type=TaskType.STRUCTURED_OUTPUT`), falling back to resilient rule-based mitigation options on LLM provider errors.
    * **LangGraph Integration**: Wired real `recommendation_node` into the StateGraph DAG, connecting into `hitl_gate`.
  - 23 unit tests in `tests/unit/test_recommendation_agent.py` achieving **100% statement and branch coverage** (428 statements).

### Phase 10: HITL Approval System
- **P10-1 · HITL Service (`feature/hitl-approval-service`)**: Completed ✅
  - `src/services/hitl_service.py`: Implemented centralized Human-in-the-Loop approval service (`HITLService`), data models (`ApprovalCreateInput`), custom exceptions (`HITLServiceError`, `ApprovalNotFoundError`, `UnauthorizedSignerError`, `InvalidApprovalOperationError`, `TokenReplayServiceError`, `TokenExpiredServiceError`, `TokenVerificationServiceError`), and thread-safe singleton accessor (`get_hitl_service()`):
    * **The Triad of Responsibility (BR-RULE-001)**: Pure deterministic Python arithmetic with `Decimal` precision (`NUMERIC(14,2)`). Standard Python floats are strictly rejected with `TypeError` to prevent precision drift.
    * **Spend Governance Tiers & Deterministic TTL**:
      - Tier 1 (`CATEGORY_MGR`): Spend <= $25,000 (1-hour TTL, single signature).
      - Tier 2 (`PROC_DIRECTOR`): Spend $25,001 - $100,000 (1-hour TTL, single signature).
      - Tier 3 (`DUAL_VP`): Spend > $100,000 (30-minute TTL, dual distinct executive signatures: Director + VP Supply Chain).
    * **Cryptographic Token Issuance & Verification**: Issues AWS KMS ECDSA P-256 tokens (`HITLTokenService`) and verifies cryptographic validity, binding parameters (action_id, alert_id, amount_usd), and expiration timestamps.
    * **Anti-Replay Protection**: Verifies token uniqueness against Aurora PostgreSQL/SQLite `HITLApproval` repository using unique `token_hash` index, raising `TokenReplayServiceError` on repeated usage.
    * **Dual-Approval Coordination**: Verifies two distinct executive tokens for Tier 3 spend; rejects identical signers (`UnauthorizedSignerError`) and action mismatches.
    * **Full Database Lifecycle**: `create_approval_request`, `sign_approval` (transitions `PENDING` -> `PARTIALLY_APPROVED` -> `APPROVED`), `reject_approval`, `get_approval` (automatically transitions expired records to `EXPIRED`), and `list_pending_approvals`.
  - Updated `src/services/__init__.py` exporting all HITL service classes and exceptions.
  - 23 offline unit tests in `tests/unit/test_hitl_service.py` achieving **98% statement coverage** (201 statements), bringing total test suite to 652 passing tests (97.65% project-wide coverage).

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
15. **Repository-Level Append-Only Enforcement & Anti-Replay Lookups**:
    - Repository layer guarantees that audit logs can never be mutated or deleted via code, while cryptographic token lookups allow O(1) replay detection before human approvals are processed.
16. **Cryptographic Anti-Replay Token Immutability & Indexing**:
    - Physical database unique index `idx_hitl_approvals_token_hash` guarantees that any re-submitted KMS ECDSA signature token is unconditionally rejected by Aurora PostgreSQL, preventing fraudulent mitigation execution.
17. **Canonical k-NN Vector Indexing & Hybrid Query Isolation**:
    - OpenSearch document embeddings are strictly mapped to HNSW cosine similarity indices with 1536-dimensional dense vectors, combining vector distance search with boolean metadata filters without leaking raw un-sanitized supplier text.
18. **Enterprise OIDC/Okta Identity & RBAC Hierarchy Enforcement**:
    - All API routes and sensitive capabilities are gated behind cryptographic JWT verification and role hierarchy guards (`analyst` < `category_manager` < `procurement_director` < `vp_supply_chain` < `system_admin`), normalizing claim extractions across Okta (`groups`), Keycloak (`realm_access.roles`), and OAuth2 (`scp`), rejecting expired, unauthenticated, or under-privileged requests with standardized 401/403 error envelopes.
19. **Cryptographic KMS ECDSA P-256 HITL Spend Governance & Dual Sign-Off**:
    - Consequential spend commitments and mitigation dispatches strictly require AWS KMS ECDSA P-256 cryptographic signatures, bound immutably to action ID, alert ID, and monetary amount. Spend <= $100k is granted a 1-hour TTL single token; spend > $100k strictly requires dual sign-off from two distinct executives with a 30-minute TTL, while SHA-256 token hashing guarantees zero replay attacks across database transactions.

20. **Deterministic Persona Token Emulation & RBAC Tier Alignment**:
    - Pre-configured demo authentication tokens emulate production Okta OIDC JWTs, binding explicit user IDs, emails, roles, and groups to strict monetary spend limits (analyst $0, category manager $25k, procurement director $100k, VP supply chain dual-signoff, admin system-only). Lower-tier tokens are blocked from elevated operations by FastAPI RBAC guards, preventing test-environment privilege drift.

21. **Deterministic Spend-Tier Routing & Dual Executive Sign-Off Enforcement**:
    - Financial commitment actions are strictly routed to governance tiers based on deterministic `Decimal` amount evaluation. Amounts <= $25,000 require Category Manager approval (1-hr TTL); amounts between $25,001 and $100,000 require Procurement Director approval (1-hr TTL); amounts > $100,000 unconditionally require dual sign-off from two distinct executives (Procurement Director + VP Supply Chain, 30-min TTL), rejecting single-signer authorization with standard 403 `INSUFFICIENT_ROLE` error envelopes.

22. **Autonomous Transaction Decoupling for Append-Only Audit Trails (BR-RULE-007)**:
    - Forensic audit records in `audit_logs` are executed strictly within dedicated, independent `AsyncSession` instances, decoupling them from caller transactions. If a business workflow fails, rejects authorization, or triggers a database rollback, the audit log of the attempt remains permanently committed. Credential fields (`token`, `secret`, `password`, `key`) are automatically redacted prior to persistence.

23. **Neptune OpenCypher Resilience, Connection Pooling & Injection Defense (SEC-024)**:
    - Amazon Neptune OpenCypher queries are executed asynchronously via `httpx.AsyncClient` with bounded connection pooling (max 100 connections, 20 keepalive). All parameters are bound natively in JSON request bodies to prevent Cypher query injection. Transient network and cluster failures (429, 500, 502, 503, 504) are subject to exponential backoff retries (3 retries: 0.5s, 1.0s, 2.0s) with strict 5.0s query timeout (`GRAPH_504_TIMEOUT`). Circuit breaker pattern trips after 5 consecutive failures, fail-fasting to cached graph topology and preventing cascading dependency collapse.

24. **Idempotent Graph Schema Seeding & Structural Integrity (SEC-025)**:
    - All Amazon Neptune Knowledge Graph seeding operations are executed via deterministic OpenCypher `MERGE` clauses with parameter bindings, preventing node duplication and edge proliferation across repeated runs. The seeder service (`src/graph/seed.py`) enforces strict schema topologies across all mandatory automotive entities (`Supplier`, `Component`, `Plant`, `Contract`, `NewsEvent`, `GeopoliticalRisk`, `Assembly`, `Program`) and multi-tier relationship types (`SUPPLIES`, `SUPPLIES_PART`, `USED_BY`, `TIER_1_OF`, `PART_OF_BOM`, `ASSEMBLED_AT`, `ALLOCATED_TO`, `BOUND_BY`, `AFFECTS`, `THREATENS`), verified by programmatic integrity auditing.

25. **Immutable Parameterized Cypher Query Catalog (SEC-026)**:
    - All OpenCypher queries executed against Amazon Neptune must be constructed through `CypherQuery` and `CypherQueryLibrary` (`src/graph/queries/`). Queries use strict parameter binding (`$supplier_id`, `$component_id`, etc.) with programmatic validation enforcing that required parameters are supplied and non-null before query execution. Dynamic string interpolation and concatenation of user or agent input into Cypher syntax is strictly prohibited, eliminating Cypher injection vulnerabilities across all graph traversal workflows.

26. **Bounded Multi-Tier Supply Chain Traversal & Blast Radius Isolation (SEC-027)**:
    - Multi-tier supply chain traversals in `SupplierTraversalService` (`src/graph/traversal.py`) are strictly bounded to prevent graph recursion denial-of-service and cycle-induced memory exhaustion. Tier chains (`TIER_1_OF`) are capped at 1..4 hops, subgraphs are restricted to 2-hop ego boundaries with node and edge deduplication in memory, and query execution is governed by a 5.0-second deadline. Downstream disruption blast radius maps shortest-path impacts across components, consuming assembly plants, and vehicle programs without executing probabilistic LLM operations or arithmetic calculations in the graph tier (BR-RULE-001).

27. **Deterministic 5-Hop Disruption Path & Single-Source Boundary Isolation (SEC-028)**:
    - Multi-hop supply chain disruption investigations validate exact 5-hop path trajectories (`Origin Signal -> Supplier -> Component -> Assembly -> Plant -> Program`), establishing causal lineage from external incidents to end-product vehicle programs. Single-source dependency detection strictly isolates sole-source bottleneck components (`supplier_count == 1` or `is_single_source == true`) from multi-sourced redundant components, preventing false-positive escalation of emergency spot-buy workflows. All graph queries strictly honor the 2.0-second p95 latency SLO and 5.0-second hard deadline with circuit breaker protection.
28. **At-Least-Once Delivery Semantics & Dead-Letter Forensic Guarantees (SEC-029)**:
    - Streaming event consumers (`src/kafka/consumer.py`) strictly commit partition offsets manually and only after successful business handler completion or successful persistence to `<topic>.dlq`. Transient processing exceptions trigger up to 3 retried attempts before routing to the dead-letter queue. If DLQ publication fails, partition offsets are never committed, guaranteeing zero message loss and complete at-least-once delivery semantics across distributed broker partitions.
29. **Distributed Event Publication Reliability & Precision Preservation (SEC-030)**:
    - Streaming event publishing (`src/kafka/producer.py`) strictly enforces `acks="all"`, synchronous broker confirmation (`future.get(timeout)`), and automated JSON serialization preserving `Decimal` monetary precision (BR-RULE-001) as strings without IEEE 754 float distortion. Domain partition keys (`supplier_id`, `action_id`, `entity_id`) guarantee total event ordering across broker partitions, while distributed trace identifiers (`X-Trace-ID`, `X-Client-ID`, `X-Timestamp`) ensure end-to-end observability across the Kafka event bus.
30. **Strict Schema Boundaries, Monetary Precision & PII Sanitization (SEC-031)**:
    - All streaming events across Apache Kafka MSK topics strictly adhere to Pydantic v2 event contracts (`src/kafka/schemas/`) with `extra="forbid"`, preventing untrusted field injection. Financial commitments and inventory metrics strictly enforce `Decimal` precision, serializing to exact strings in JSON payloads to prevent floating-point distortion. Forensic audit events automatically redact credentials (`password`, `token`, `secret`, `kms_key`), and HITL authorization requests deterministically enforce spend-tier thresholds and required dual executive sign-offs prior to message publishing.
31. **Idempotent Streaming Ingestion & Database Transaction Integrity (SEC-032)**:
    - Kafka event consumers persisting data to Aurora PostgreSQL (`src/kafka/handlers.py`) guarantee strict idempotency by inspecting existing records prior to insertion and performing atomic in-place updates. Transaction boundaries strictly commit before Kafka manual offset commits, and transaction rollbacks trigger exception bubbling to consumer retries. Poisonous or corrupt messages fail gracefully into dead-letter queues (`<topic>.dlq`) without committing unhandled offsets, guaranteeing at-least-once delivery with zero duplicate database corruption.
32. **The Triad of Responsibility & Strict Decimal Precision Invariant (SEC-033)**:
    - 100% of supply chain risk calculations (`src/services/risk/calculator.py`) run in pure deterministic Python. AI agents and LLMs are strictly forbidden from performing inventory or financial arithmetic (BR-RULE-001). All fractional, currency, and inventory numbers are represented as `Decimal` with `ROUND_HALF_UP` rounding, eliminating floating-point drift and IEEE 754 precision loss. Physical inventory constraints strictly reject negative inputs (`stock < 0`, `rate < 0`, `ETA < 0`, `cost < 0`), zero consumption is capped at 999.00 days, and every calculation emits a reproducible SHA-256 verification token.
33. **Deterministic Risk Severity Assignment & Spend Gate Governance (SEC-034)**:
    - Pure deterministic Python risk classification (`src/services/risk/scorer.py`) strictly assigns severity levels (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) from exact Decimal gap and exposure thresholds (`CRITICAL`: gap > 0 and exposure > $1M; `HIGH`: gap > 0 and exposure > $250k; `MEDIUM`: gap > 0 or supplier risk score > 0.70; `LOW`: gap <= 0 and score <= 0.70). All monetary exposures are mapped deterministically to cryptographic AWS KMS HITL spend tiers (Category Manager <= $25k, Procurement Director <= $100k, Dual VP > $100k), enforcing BR-RULE-001 by completely isolating risk categorization from probabilistic AI hallucination.
34. **Physical Inventory Underflow, Layered Caching & Outage Resilience (SEC-035)**:
    - Deterministic stock aggregation in `src/services/risk/inventory_service.py` enforces strict Decimal precision across all balances, burn rates, and valuations, rejecting negative underflows with `InvalidInventoryOperationError` (BR-RULE-001). Caching adheres to LLD Section 6.1 with 30-minute TTL (1800s) and cache-through synchronization on updates. Dual circuit-breaker degradation protects against distributed partitions: Redis timeouts gracefully fall back to Aurora PostgreSQL direct queries, while database partitions fall back to Redis cached balances, preventing cascading pipeline halts.
35. **Canonical Golden Benchmark Enforcement & Build-Failure Guard (SEC-037)**:
    - All risk engine arithmetic, severity classification, and spend-tier routing must pass the canonical NanoCore reference scenario (`tests/golden/nanocore_scenario.json`) with 100% mathematical precision (`days_of_cover=7.68`, `gap_days=1.32`, `shortage_volume=24420`, `financial_exposure=$2,448,105.00`, `factory_halt_exposure=€2,692,800.00`, `total_exposure=$5,140,905.00`, `severity=CRITICAL`, `HITL=DUAL_VP`). Per CLAUDE.md Section 14, if `test_nanocore_golden()` fails, the build fails unconditionally, ensuring zero regression of The Triad of Responsibility (BR-RULE-001).
36. **Unified Model Routing, Automated Fallback & Exact Token Cost Tracking (SEC-038)**:
    - Unified LiteLLM gateway (`src/llm/gateway.py`) routes completions according to task complexity (Bedrock Claude 3.5 Sonnet for synthesis/general, Claude 3.5 Haiku for triage/extraction). Automatically fails over to the fallback model on 429 RateLimit, 503 ServiceUnavailable, or 504 Timeout errors without cascading exceptions to calling workflows. Standardizes third-party exceptions into domain errors (`LLMRateLimitError`, `LLMTimeoutError`, etc.). Computes exact monetary costs in `Decimal` ($0.000001 precision per 1M tokens) enforcing BR-RULE-001, maintains running cumulative ledgers across threads, and propagates distributed `trace_id` metadata.
37. **Untrusted External Text Quarantine & Passive XML Delimiter Encapsulation (SEC-039, BR-RULE-007)**:
    - All external text (supplier contracts, news feeds, SEC disclosures, emails) must pass through `QuarantinedReader` before inclusion in any LLM prompt (CLAUDE.md Sec 8.1). Strips non-printable ASCII characters (`[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]`), cleans HTML/XML, neutralizes delimiter breakout tags (`</untrusted_supplier_data>`, `<untrusted_signal>`, `<system>`, `<instructions>`), detects and redacts high-risk prompt injection directives, enforces max token budgets with binary search truncation, computes deterministic SHA-256 hashes, encapsulates content in `<untrusted_supplier_data>`, and writes immutable forensic records to `audit_logs` (BR-RULE-007).
38. **Pydantic Schema Output Enforcement & Free-Text Rejection (SEC-040)**:
    - All LLM completions consumed by agent nodes must strictly adhere to typed Pydantic v2 schemas (`Citation`, `ResearchAnalysis`, `ContractAnalysis`, `RiskNarrative`, `MitigationScenario`, `RecommendationReport`, `IncidentCaseDossier`). Free-text responses and non-JSON output are rejected with `StructuredOutputParsingError` (HTTP 422 RFC 7807). Schemas enforce `extra="forbid"` to eliminate prompt-injection attribute pollution, validate that all monetary amounts and penalties use Python `Decimal` (BR-RULE-001), guarantee net financial benefit arithmetic consistency, and forbid bypassing human spend gates (`requires_hitl=True` when cost > 0).
39. **Confidential Contract Data Sovereignty & VPC-Only Ingestion Gate (SEC-041, NFR-SEC-02)**:
    - Supplier contracts and agreements governed by EU/EEA jurisdictions (32 member states), classified as `CONFIDENTIAL`, `HIGHLY_CONFIDENTIAL`, or `RESTRICTED`, or explicitly flagged as `is_eu_regulated` or `is_confidential` must NEVER leave the private VPC or be transmitted to external multi-tenant model APIs (such as Amazon Bedrock Claude).
    - Data sovereignty routing (`ConfidentialContractRouter`) directs these agreements exclusively to private self-hosted vLLM GPU clusters (2x g6e.12xlarge on AWS EKS).
    - Attempting to route sovereign contracts to external providers triggers `VLLMDataSovereigntyViolationError` (HTTP 403 `DATA_SOVEREIGNTY_VIOLATION`).
    - All contract texts are hashed via SHA-256 for audit logging (BR-RULE-007), and raw text is strictly shielded from unencrypted stdout or application logs.

40. **Deterministic Offline LLM Isolation & Schema-Compliant Fixtures (SEC-042, CLAUDE.md Sec 14)**:
    - In accordance with offline-first testing mandates (CLAUDE.md Sec 14, GEMINI.md, Rule 8), automated tests must execute without external network socket I/O to Amazon Bedrock, vLLM, or external LLM endpoints.
    - Setting `USE_MOCK_LLM=true` (or `use_mock=True`) routes all LLM gateway and agent completion requests to `MockLLMClient`, returning deterministic schema-valid JSON fixtures matching P8-3 Pydantic models (`ResearchAnalysis`, `ContractAnalysis`, `RiskNarrative`, `RecommendationReport`, `IncidentCaseDossier`).
    - The mock client provides thread-safe FIFO response queuing, dynamic per-schema overrides, and context-aware schema inference from prompt keywords, strictly preserving `Decimal` monetary precision (BR-RULE-001) with zero cost drift.

41. **Deterministic Multi-Agent StateGraph DAG & Reducer Isolation (SEC-043, LLD Sec 4.2)**:
    - Multi-agent investigation workflows are strictly orchestrated as bounded directed acyclic graphs in LangGraph (`src/agents/graph.py`).
    - Node transitions are deterministically evaluated through pure Python conditional routing functions (`route_after_triage`, `route_after_risk`, `route_after_hitl_gate`), eliminating recursion loops and guaranteeing the 90-second investigation SLO (NFR-PERF-01).
    - State modification is governed by strongly-typed `SupplierRiskState` channels with additive reducers (`operator.add`) for audit trails and errors.
    - Quantitative risk calculations remain completely isolated from probabilistic agent reasoning (BR-RULE-001), and spend commitments > $0 unconditionally halt at `hitl_gate` until cryptographically verified approval tokens are submitted.

42. **Deterministic Signal Triage, Input Quarantine & Multi-Path Routing (SEC-044, BR-RULE-001)**:
    - Signal triage (`src/agents/nodes/triage_agent.py`) is 100% deterministic Python rule and keyword evaluation (zero LLM calls and zero LLM arithmetic).
    - All untrusted disruption signals are strictly pre-sanitized through `QuarantinedReader`, stripping control characters, script/style blocks, HTML tags, and neutralizing delimiter breakout tags before mutating state.
    - Signals are categorized into news, financial, logistics, and geopolitical taxonomies with bounded confidence scoring.
    - Automated zero-impact blast radius detection routes benign events immediately to `NODE_DISMISS`, saving LLM compute.
    - Multi-signal disruptions (e.g., bankruptcy + fire) dynamically fan out to both `NODE_RESEARCH` and `NODE_CONTRACT` in parallel branches before converging into quantitative risk assessment (`NODE_RISK`).

43. **External Intelligence Quarantine & Structured Research Synthesis (SEC-045, CLAUDE.md Sec 8.1)**:
    - All intelligence gathering tools (`NewsScraperTool`, `SECEDGARTool`, `GeopoliticalAPITool` in `src/agents/tools/research_tools.py`) strictly enforce pre-exposure text quarantine via `QuarantinedReader`.
    - Unsanitized external text is prohibited from mutating `SupplierRiskState` evidence channels or entering LLM prompts.
    - Research synthesis produces strongly-typed `ResearchAnalysis` models (P8-3) with verifiable citations and source provenance.
    - Agent execution incorporates deterministic rule-based fallback synthesis, guaranteeing uninterrupted workflow progression during LLM provider rate limits or service degradation.

44. **Confidential Contract VPC Isolation, Sovereign Data Residency & Legal Extraction (SEC-046, NFR-SEC-02)**:
    - Supplier contract analysis (`src/agents/nodes/contract_agent.py`) strictly enforces data sovereignty boundaries through `ConfidentialContractRouter`. All contracts governed by EU/EEA jurisdictions (32 member states), classified as `CONFIDENTIAL`, `HIGHLY_CONFIDENTIAL`, or `RESTRICTED`, or explicitly flagged as `is_eu_regulated` or `is_confidential` are routed exclusively to self-hosted vLLM GPU clusters within the private VPC. Attempting to route sovereign contracts to external cloud providers (Bedrock) raises `VLLMDataSovereigntyViolationError` (HTTP 403 `DATA_SOVEREIGNTY_VIOLATION`).
    - All raw contract texts pass through `QuarantinedReader.sanitize()` with SHA-256 hashing before processing, stripping malicious injection payloads and HTML/script tags.
    - Outputs conform strictly to Pydantic v2 `ContractAnalysis` models with exact `Decimal` precision for delay penalty percentages and liability caps (BR-RULE-001).
    - Features deterministic fallback synthesis on vLLM service disruptions, ensuring workflow continuity without sacrificing safety.

45. **The Triad of Separation & Qualitative Narrative Synthesis (SEC-047, BR-RULE-001)**:
    - Risk assessment (`src/agents/nodes/risk_agent.py`) strictly enforces the architectural boundary between deterministic computation and qualitative AI explanation. 100% of arithmetic calculations (`days_of_cover`, `gap_days`, `shortage_volume`, `financial_exposure`, `factory_halt_exposure`, `total_exposure`) run in pure deterministic Python microservices (`RiskCalculator` and `RiskScorer`) using exact `Decimal` precision.
    - LLMs and probabilistic agents are strictly forbidden from performing arithmetic. Pre-computed mathematical outputs and severity ratings are passed to LiteLLM Gateway (`TaskType.SYNTHESIS`, Claude 3.5 Sonnet) solely to contextualize the operational impact into typed Pydantic `RiskNarrative` models (`executive_summary`, `root_cause_analysis`, `operational_impact`, `runway_and_exposure_commentary`, `citations`).
    - Deterministic rule-based fallback synthesis guarantees that LLM timeout or degradation never halts the StateGraph pipeline.

46. **Mitigation Option Formulation & Spend Tier Governance (SEC-048, BR-RULE-001)**:
    - Recommendation formulation (`src/agents/nodes/recommendation_agent.py`) enforces strict Human-in-the-Loop spend gates. While generative AI proposes and ranks alternative mitigation scenarios (e.g., spot-buys from broker networks, expedited air freight charters, regional buffer reallocations), probabilistic models are strictly forbidden from auto-approving or auto-executing financial commitments.
    - Any mitigation scenario with financial spend (`estimated_cost_usd > $0.00`) mandates human authorization (`requires_hitl=True`) and deterministically resolves governing spend tiers (`get_spend_tier()`: Category Manager <= $25k, Procurement Director <= $100k, Dual VP > $100k).
    - Mathematical consistency enforces exact `Decimal` precision where `net_financial_benefit_usd == avoided_loss_usd - estimated_cost_usd`.
    - Workflows suspend at `hitl_gate` in `WorkflowStatus.AWAITING_APPROVAL` status when human sign-off is required, routing to `END` until cryptographic ECDSA authorization tokens are provided.
    - Resilient deterministic fallback guarantees pipeline continuity during LLM provider latency or outages.

47. **Cryptographic Approval Token Verification & Spend Authority Gates (SEC-049, BR-RULE-001)**:
    - Capital authorization and operational mitigation actions are strictly gated by AWS KMS ECDSA P-256 cryptographic tokens managed by `HITLService` (`src/services/hitl_service.py`).
    - Monetary thresholds are governed by pure Python deterministic routing (`src/core/spend_tier_router.py`), completely isolating authorization rules from LLM reasoning. Floating-point inputs are strictly rejected to prevent precision drift.
    - Token TTL is deterministically bound: 1 hour for Tiers 1-2, and shortened to 30 minutes for Tier 3 executive dual approvals.
    - Replay attacks are prohibited through SHA-256 unique `token_hash` indexing and verification against Aurora PostgreSQL/SQLite repositories before state transitions are committed.
    - Dual sign-off enforces distinct executive identities (`UnauthorizedSignerError` on duplicate signers), ensuring no single actor can unilaterally dispatch Tier 3 capital commitments (> $100,000).

48. **Dual Executive Sign-Off Enforcement on High-Value Disruption Mitigations (SEC-050, BR-RULE-001)**:
    - Actions committing capital > $100,000 (Tier 3 / `DUAL_VP`) require two independent, valid cryptographic KMS ECDSA P-256 tokens from distinct executive signers (Procurement Director + VP Supply Chain) with 30-minute TTLs.
    - Strict enforcement of CLAUDE.md Sec 20.1 invariant: *"A DUAL_VP action proceeding with only one approval signature must NEVER happen."*
    - Single signature on a `DUAL_VP` action transitions workflow status to `PARTIALLY_APPROVED` and keeps the StateGraph paused at `await_approval` (routing to `END`).
    - `action_node` enforces a hard pre-execution gate via `enforce_action_execution()`, raising `InsufficientSignaturesError` if fewer than two valid signatures are present, guaranteeing zero automated or single-signature execution bypass.
    - Pure deterministic Python arithmetic with `Decimal`, strictly rejecting native floats with `TypeError`.
    - 18 comprehensive unit tests in `tests/unit/test_dual_approval_enforcer.py` achieving 91% coverage under strict offline isolation (zero live AWS or network calls).

49. **Cryptographic Token Anti-Replay Governance & Forensic Security Alerting (SEC-051, BR-RULE-001, BR-RULE-007)**:
    - `TokenReplayGuard` (`src/services/token_replay_guard.py`) enforces strict uniqueness of all KMS ECDSA P-256 authorization tokens prior to and during database persistence.
    - Database verification queries `hitl_approvals.token_hash` unique index (`idx_hitl_approvals_token_hash`).
    - Multi-token intra-batch verification intercepts duplicate token hashes within a single multi-signature request payload, blocking anti-self-replay in `DUAL_VP` workflows before database operations.
    - Database race condition defense wraps approval creation (`wrap_create_approval`), intercepting concurrent duplicate inserts (`IntegrityError` / `TokenReplayError`) and dispatching security alerts.
    - High-severity security alerting (`"SECURITY ALERT: Cryptographic token replay attempt detected!"`) immediately logs forensic details and calls registered security callbacks.
    - Forensic audit durability (BR-RULE-007): Dispatches isolated `write_audit_log` with `action="SECURITY_TOKEN_REPLAY_ATTEMPT"`, ensuring forensic evidence is committed to Aurora PostgreSQL / SQLite even if outer workflow transactions roll back.
    - 14 automated unit tests in `tests/unit/test_token_replay_guard.py` achieving 95% statement coverage under strict offline isolation.

50. **Comprehensive End-to-End HITL Security Verification & Anti-Bypass Gates (SEC-052, BR-RULE-001, CLAUDE.md Sec 14 & 20.1)**:
    - Complete matrix test suite in `tests/unit/test_hitl_unit_tests.py` (19 unit tests, 100% pass) rigorously proving the 5 mandatory acceptance criteria across all system boundaries:
      * **Valid Token Lifecycle**: Tier 1 (Category Manager $\le \$25,000$, 1-hr TTL), Tier 2 (Procurement Director $\$25,001 - \$100,000$, 1-hr TTL), and Tier 3 (Dual VP $> \$100,000$, 30-min TTL) cryptographically sign and transition approval status to `APPROVED`.
      * **Temporal Expiration**: Immediate rejection across `HITLTokenService` (`TokenExpiredError`), `HITLService` (`TokenExpiredServiceError`), and `DualApprovalEnforcer` (`DualApprovalExpiredError`).
      * **Token Replay Prevention**: Unique constraint lookup and intra-batch anti-self-replay detection raise `TokenReplaySecurityAlert` and record forensic security audit logs.
      * **Strict Parameter Binding**: Cryptographic tokens bound to action ID, risk alert ID, or amount USD cannot be repurposed; mismatched parameters trigger `TokenBindingMismatchError` and `DualApprovalActionMismatchError`.
      * **Dual-Approval Enforcer Hard Execution Gate**: Actions committing $> \$100,000$ with single signature transition to `PARTIALLY_APPROVED`, conditional edge `route_after_hitl_gate` routes to `await_approval` (`END`), and direct execution in `action_node` strictly raises `InsufficientSignaturesError`. Enforces invariant: *"A DUAL_VP action proceeding with only one approval signature must NEVER happen."*
      * **Precision & RBAC**: Rejects native floats with `TypeError` per BR-RULE-001, rejects unauthorized roles (`analyst`) with `UnauthorizedSignerError`, and rejects tampered signatures with `TokenSignatureInvalidError`.

51. **Deterministic API Route Layering & Alert Governance (SEC-053, BR-RULE-001, CLAUDE.md Sec 5.2 & Sec 10)**:
    - **The Triad of Separation Invariant (BR-RULE-001)**: `POST /api/v1/risk/evaluate` strictly delegates 100% of arithmetic operations to deterministic Python services (`RiskCalculator.calculate_from_params()` and `compute_risk_level()`). Route handlers never perform business arithmetic directly.
    - **Fast-Track vs Full-Track Pipeline Routing**: Disruption evaluations with zero shortage gap (`gap_days <= 0.00`) and low severity deterministically classify as `FAST_TRACK`, returning immediate calculation responses with zero agent latency. Disruptions with positive shortage gaps and exposure auto-route to `FULL_TRACK`. Explicit `pipeline_mode` overrides are honored.
    - **RBAC Authority Boundaries**: Evaluation and feed querying (`POST /api/v1/risk/evaluate`, `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`) mandate `require_role(UserRole.ANALYST)` or higher. Consequential alert status transitions (`POST /api/v1/alerts/{id}/acknowledge`) mandate `require_role(UserRole.CATEGORY_MANAGER)`, strictly rejecting `analyst` with HTTP 403 `INSUFFICIENT_ROLE`.
    - **Rolling Window Deduplication & Anti-Flooding**: Integrates `RiskAlertRepository.find_recent_active_alert()` to collapse repeated evaluations for the same SKU and supplier within a 1-hour window, updating existing exposure metrics and returning `status="COLLAPSED"` to prevent alert table bloat.
    - **Terminal Status Protection**: Alerts in terminal statuses (`RESOLVED`, `CLOSED`, `DISMISSED`) reject acknowledgement attempts with HTTP 409 `CONFLICT`.
    - **Append-Only Forensic Audit Trail (BR-RULE-007)**: Dispatches immutable audit records via `write_audit_log()` on evaluation (`RISK_EVALUATION_EXECUTED`) and acknowledgement (`ALERT_ACKNOWLEDGED`) with graceful error containment.
    - **Validation & Error Standards**: Pydantic v2 schemas with `extra="forbid"`, UUID format validation (`400 VALIDATION_ERROR`), and standardized RFC 7807 error envelopes masking internal traces.
    - **Comprehensive Test Suite**: 23 unit tests in `tests/unit/test_risk_routes.py` achieving 89% route statement coverage and 100% pass rate under strict offline isolation.

---

## 5. Next Planned Tasks
- **Phase 8 — LLM Foundation (LiteLLM Gateway & Guardrails)**: Completed ✅ (5/5 tasks done)
- **Phase 9 — Multi-Agent System (LangGraph Orchestration)**: Completed ✅ (6/6 tasks done)
  - **P9-1**: LangGraph `AgentState` and `StateGraph` skeleton (`src/agents/state.py`, `src/agents/graph.py`) (`feature/agents-langgraph-skeleton`). Completed ✅
  - **P9-2**: Triage agent node (`src/agents/nodes/triage_agent.py`) (`feature/agents-triage-node`). Completed ✅
  - **P9-3**: Research agent node (`src/agents/nodes/research_agent.py`) (`feature/agents-research-node`). Completed ✅
  - **P9-4**: Contract agent node (`src/agents/nodes/contract_agent.py`) (`feature/agents-contract-node`). Completed ✅
  - **P9-5**: Risk agent node (`src/agents/nodes/risk_agent.py`) (`feature/agents-risk-node`). Completed ✅
  - **P9-6**: Recommendation agent node (`src/agents/nodes/recommendation_agent.py`) (`feature/agents-recommendation-node`). Completed ✅
- **Phase 10 — HITL Approval System**: Completed ✅ (4/4 tasks done)
  - **P10-1**: HITL service (`src/services/hitl_service.py`) — issues KMS ECDSA tokens, routes to correct spend tier, enforces 1-hour / 30-minute TTL (`feature/hitl-approval-service`). Completed ✅
  - **P10-2**: Dual-approval enforcer (`feature/hitl-dual-approval-enforcer`). Completed ✅
  - **P10-3**: Token replay guard (`feature/hitl-token-replay-guard`). Completed ✅
  - **P10-4**: HITL unit tests (`feature/hitl-unit-tests`). Completed ✅
- **Phase 11 — FastAPI API Routes**:
  - **P11-1**: Fast-track / Full-track pipeline routes (`src/api/routes/risk_routes.py`) (`feature/api-alert-routes`). Completed ✅
  - **P11-2**: Investigation routes — `POST /api/v1/investigations/start`, `GET /api/v1/investigations/{id}` (`feature/api-investigation-routes`). Next 🔄




