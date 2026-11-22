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
| **Phase 4 Progress** | 2 / 5 Tasks Completed | In Progress 🔄 |
| **Total Test Suites** | 18 (`test_project_structure.py`, `test_config.py`, `test_logging.py`, `test_api_skeleton.py`, `test_health_routes.py`, `test_ci_pipeline.py`, `test_docker_compose.py`, `test_localstack_bootstrap.py`, `test_redpanda_topics.py`, `test_neptune_emulation.py`, `test_makefile.py`, `test_database_models.py`, `test_database_migrations.py`, `test_database_repositories.py`, `test_token_hash_index.py`, `test_opensearch_client.py`, `test_security_rbac.py`, `test_hitl_tokens.py`) | PASSED ✅ |
| **Total Test Cases** | 137 unit/golden tests | 100% Passing (0 failures) |
| **Code Coverage (`src/`)** | **91%** statement coverage (`src/core/hitl_tokens.py` at 100%) | Exceeds 80% DoD gate |
| **Active Branch** | `feature/security-hitl-token-service` $\to$ `development` | Clean |

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

---

## 5. Next Planned Tasks
- **Phase 5 — Knowledge Graph (Amazon Neptune)**:
  - **P5-1**: Neptune OpenCypher client (`src/graph/neptune_client.py`) — connection pool, query executor, retry logic (`feature/graph-neptune-client`).
  - **P5-2**: Graph schema seed — `Supplier`, `Component`, `Plant`, `Contract`, `NewsEvent`, `GeopoliticalRisk` nodes + all relationships (`feature/graph-schema-seed`).
  - **P5-3**: Named Cypher query library (`src/graph/queries/`) — supplier-to-component, component-to-plant, tier-chain traversal (`feature/graph-cypher-queries`).
  - **P5-4**: Supplier traversal service (`src/graph/traversal.py`) — shortest-path disruption -> affected SKUs -> affected plants (`feature/graph-traversal-service`).
  - **P5-5**: Graph traversal unit tests — mock Neptune responses, assert 5-hop path and single-source dependency detection (`feature/graph-traversal-tests`).
