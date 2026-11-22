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
| **Total Test Suites** | 30 (`test_project_structure.py`, `test_config.py`, `test_logging.py`, `test_api_skeleton.py`, `test_health_routes.py`, `test_ci_pipeline.py`, `test_docker_compose.py`, `test_localstack_bootstrap.py`, `test_redpanda_topics.py`, `test_neptune_emulation.py`, `test_makefile.py`, `test_database_models.py`, `test_database_migrations.py`, `test_database_repositories.py`, `test_token_hash_index.py`, `test_opensearch_client.py`, `test_security_rbac.py`, `test_hitl_tokens.py`, `test_demo_tokens.py`, `test_spend_tier_router.py`, `test_audit_writer.py`, `test_neptune_client.py`, `test_graph_seed.py`, `test_cypher_queries.py`, `test_supplier_traversal.py`, `test_graph_traversal_paths.py`, `test_kafka_consumer.py`, `test_kafka_producer.py`, `test_kafka_schemas.py`, `test_kafka_consumer_integration.py`) | PASSED ✅ |
| **Total Test Cases** | 318 tests (307 unit + 11 integration) | 100% Passing (0 failures) |
| **Code Coverage (`src/`)** | **96.08%** statement coverage (`src/kafka/handlers.py` and `src/kafka/schemas/` at 100%) | Exceeds 80% DoD gate |
| **Active Branch** | `feature/kafka-consumer-integration-test` $\to$ `development` | Clean |

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

---

## 5. Next Planned Tasks
- **Phase 7 — Deterministic Risk Engine**:
  - **P7-1**: Risk calculator (`src/services/risk/calculator.py`) — Days of Cover, gap days, shortage volume, financial exposure — all `Decimal`, zero float (`feature/risk-calculator-core`).
  - **P7-2**: Risk scorer (`src/services/risk/scorer.py`) — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` assignment from gap + exposure thresholds (`feature/risk-scorer`).
  - **P7-3**: Inventory aggregation service (`src/services/risk/inventory_service.py`) — real-time stock pull from Aurora + Redis cache (`feature/risk-inventory-service`).
  - **P7-4**: Alert deduplication (`src/services/alert_service.py`) — same supplier + component within 1-hour window collapses to one alert (`feature/risk-alert-deduplication`).
  - **P7-5**: NanoCore golden tests — `tests/golden/nanocore_scenario.json` asserts `days_of_cover=7.68`, `shortage_volume=24420`, `financial_exposure=2448105.00` exactly (`feature/risk-nanocore-golden-tests`).
