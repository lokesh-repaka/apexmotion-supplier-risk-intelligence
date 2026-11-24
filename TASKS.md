# ApexMotion Supplier Risk Intelligence — Task Tracker

> Concise checklist for GitHub-visible progress.
> Architecture & Spec: [CLAUDE.md](CLAUDE.md) · HLD: [docs/HLD_ApexMotion_Supplier_Risk_Intelligence.md](docs/HLD_ApexMotion_Supplier_Risk_Intelligence.md) · LLD: [docs/LLD_ApexMotion_Supplier_Risk_Intelligence.md](docs/LLD_ApexMotion_Supplier_Risk_Intelligence.md)

**Branch convention:** `feature/<repo-name>` (one feature branch per sub-task; open the PR against `development`)
**Status:** `Pending ❌` · `In Progress 🔄` · `Completed ✅`

Sub-tasks in the same phase that do not share files can be open at the same time. Do not stack a branch on another feature branch. Merge the listed predecessor first when a row names one.

---

## Phase 1 — Runtime Skeleton

> Depends on: nothing. Unblocks: every later phase.
> Merge order: P1-1 first. P1-2 and P1-3 in parallel after it. P1-4 after P1-2. P1-5 and P1-6 in parallel last.

| Task | Branch | Status |
|------|--------|--------|
| P1-1 · Project structure, `pyproject.toml`, `frontend/package.json`, and `.env.example` | `feature/project-bootstrap` | Completed ✅ |
| P1-2 · Centralised settings (`src/core/config.py`) — all env vars via `pydantic-settings`, `get_settings()` with `lru_cache` | `feature/core-config-settings` | Completed ✅ |
| P1-3 · Structured JSON logging (`src/core/logging.py`) — `trace_id` on every log line, no PII in raw form | `feature/core-structured-logging` | Completed ✅ |
| P1-4 · FastAPI app skeleton — `src/api/main.py`, lifespan, `request_id` middleware, CORS, global exception handler | `feature/api-app-skeleton` | Completed ✅ |
| P1-5 · Health routes — `GET /health` (no I/O) and `GET /health/ready` (deep: DB, Neptune, Kafka, Redis) | `feature/api-health-routes` | Completed ✅ |
| P1-6 · GitHub Actions CI pipeline — lint (`ruff`) → type-check (`mypy`) → unit tests → Docker build | `feature/ci-github-actions` | Completed ✅ |

---

## Phase 2 — Local Dev Environment

> Depends on: P1-1. Unblocks: every phase that needs a running data store.
> Merge order: P2-1 first. P2-2, P2-3, and P2-4 in parallel after it. P2-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P2-1 · `docker-compose.yml` — PostgreSQL, Redis, Redpanda (Kafka), LocalStack (S3 + KMS), Langfuse | `feature/docker-compose-local` | Completed ✅ |
| P2-2 · LocalStack bootstrap script — creates S3 WORM bucket, KMS ECDSA key, and IAM role stubs | `feature/localstack-bootstrap` | Completed ✅ |
| P2-3 · Redpanda (local Kafka) topic creation script — `supplier-events`, `risk-alerts`, `hitl-required`, `audit-events` | `feature/kafka-topic-setup` | Completed ✅ |
| P2-4 · Neptune local emulation — Gremlin Server Docker image, seed Cypher schema, smoke-test OpenCypher query | `feature/neptune-local-emulation` | Completed ✅ |
| P2-5 · Makefile — `make run-api`, `make run-worker`, `make run-frontend`, `make test`, `make lint`, `make seed` | `feature/makefile-dev-commands` | Completed ✅ |

---

## Phase 3 — Persistence Layer (Aurora PostgreSQL)

> Depends on: P1-2 and P2-1. Unblocks: Phases 5, 7, 8, 9, 10, and 11.
> Merge order: P3-1 first. P3-2 and P3-3 in parallel after it. P3-4 after P3-2. P3-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P3-1 · SQLAlchemy 2 async models — `suppliers`, `risk_alerts`, `hitl_approvals`, `audit_logs`, `agent_runs` (`src/database/models.py`) | `feature/database-sqlalchemy-models` | Completed ✅ |
| P3-2 · Database schema DDL (`schema.sql`) and Alembic migration baseline | `feature/database-schema-migrations` | Completed ✅ |
| P3-3 · Repository layer — async CRUD for all five tables (`src/database/repositories/`) | `feature/database-repository-layer` | Completed ✅ |
| P3-4 · `hitl_approvals.token_hash` unique index — prevents replay attacks at the database level | `feature/database-token-hash-index` | Completed ✅ |
| P3-5 · OpenSearch client (`src/database/opensearch_client.py`) — k-NN vector index setup, upsert, and nearest-neighbour search | `feature/database-opensearch-client` | Completed ✅ |

---

## Phase 4 — Identity, Security & HITL Token Service

> Depends on: P1-4 and P3-1. Parallel with: nothing — P4-1 and P4-2 can run in parallel. Unblocks: Phases 6, 9, 10, 11.
> Merge order: P4-1 and P4-2 in parallel. P4-3 after P4-1. P4-4 after P4-2. P4-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P4-1 · Okta JWT validation and `require_role()` guard (`src/core/security.py`) — SAML 2.0 / OIDC | `feature/security-okta-jwt-rbac` | Completed ✅ |
| P4-2 · AWS KMS ECDSA P-256 HITL token service (`src/core/hitl_tokens.py`) — issue, sign, verify, replay detection | `feature/security-hitl-token-service` | Completed ✅ |
| P4-3 · Demo Okta tokens for `analyst`, `category_manager`, `procurement_director`, `vp_supply_chain`, `system_admin` personas | `feature/security-demo-auth-tokens` | Completed ✅ |
| P4-4 · Spend-tier router — maps action amount to HITL tier (`CATEGORY_MGR` ≤$25k / `PROC_DIRECTOR` ≤$100k / `DUAL_VP` >$100k) | `feature/security-spend-tier-router` | Completed ✅ |
| P4-5 · Append-only audit writer (`src/core/audit.py`) — immutable `audit_logs` rows, never called inside a rollback-able transaction | `feature/security-audit-writer` | Completed ✅ |

---

## Phase 5 — Knowledge Graph (Amazon Neptune)

> Depends on: P2-4 and P3-3. Parallel with: Phase 4. Unblocks: Phase 9 (agent tools).
> Merge order: P5-1 first. P5-2 and P5-3 in parallel after it. P5-4 after P5-2. P5-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P5-1 · Neptune OpenCypher client (`src/graph/neptune_client.py`) — connection pool, query executor, retry logic | `feature/graph-neptune-client` | Completed ✅ |
| P5-2 · Graph schema seed — `Supplier`, `Component`, `Plant`, `Contract`, `NewsEvent`, `GeopoliticalRisk` nodes + all relationships | `feature/graph-schema-seed` | Completed ✅ |
| P5-3 · Named Cypher query library (`src/graph/queries/`) — supplier-to-component, component-to-plant, tier-chain traversal | `feature/graph-cypher-queries` | Completed ✅ |
| P5-4 · Supplier traversal service (`src/graph/traversal.py`) — shortest-path disruption → affected SKUs → affected plants | `feature/graph-traversal-service` | Completed ✅ |
| P5-5 · Graph traversal unit tests — mock Neptune responses, assert 5-hop path and single-source dependency detection | `feature/graph-traversal-tests` | Completed ✅ |

---

## Phase 6 — Kafka Event Ingestion

> Depends on: P2-3 and P3-3. Parallel with: Phases 4 and 5. Unblocks: Phase 9 (agent trigger).
> Merge order: P6-1 first. P6-2 and P6-3 in parallel after it. P6-4 after P6-2.

| Task | Branch | Status |
|------|--------|--------|
| P6-1 · Kafka consumer (`src/kafka/consumer.py`) — MSK consumer group, at-least-once delivery, dead-letter queue on 3 failures | `feature/kafka-event-consumer` | Completed ✅ |
| P6-2 · Kafka producer (`src/kafka/producer.py`) — internal event publishing for `risk-alerts`, `hitl-required`, `audit-events` | `feature/kafka-event-producer` | Completed ✅ |
| P6-3 · Event schemas (`src/kafka/schemas/`) — `SupplierEvent`, `RiskAlert`, `HITLRequest`, `AuditEvent` JSON schemas with Pydantic validation | `feature/kafka-event-schemas` | Completed ✅ |
| P6-4 · Consumer integration test — Testcontainers Kafka, publish 3 events, assert all 3 persisted in `risk_alerts` table | `feature/kafka-consumer-integration-test` | Completed ✅ |

---

## Phase 7 — Deterministic Risk Engine

> Depends on: P3-3. Parallel with: Phases 4, 5, and 6. Unblocks: Phase 9 (risk agent node).
> Merge order: P7-1 first. P7-2, P7-3, and P7-4 in parallel after it. P7-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P7-1 · Risk calculator (`src/services/risk/calculator.py`) — Days of Cover, gap days, shortage volume, financial exposure — **all `Decimal`, zero float** | `feature/risk-calculator-core` | Completed ✅ |
| P7-2 · Risk scorer (`src/services/risk/scorer.py`) — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` assignment from gap + exposure thresholds | `feature/risk-scorer` | Completed ✅ |
| P7-3 · Inventory aggregation service (`src/services/risk/inventory_service.py`) — real-time stock pull from Aurora + Redis cache | `feature/risk-inventory-service` | Completed ✅ |
| P7-4 · Alert deduplication (`src/services/alert_service.py`) — same supplier + component within 1-hour window collapses to one alert | `feature/risk-alert-deduplication` | Completed ✅ |
| P7-5 · NanoCore golden tests — `tests/golden/nanocore_scenario.json` asserts `days_of_cover=7.68`, `shortage_volume=24420`, `financial_exposure=2448105.00` exactly | `feature/risk-nanocore-golden-tests` | Completed ✅ |

---

## Phase 8 — LLM Foundation (LiteLLM Gateway & Guardrails)

> Depends on: P1-2. Parallel with: Phases 5, 6, and 7. Unblocks: Phase 9 (all agent nodes).
> Merge order: P8-1 first. P8-2 and P8-3 in parallel after it. P8-4 after P8-2. P8-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P8-1 · LiteLLM gateway client (`src/llm/gateway.py`) — routes to Bedrock Claude 3.5 Sonnet/Haiku, fallback, rate limit, cost tracking | `feature/llm-litellm-gateway` | Completed ✅ |
| P8-2 · Quarantined Reader (`src/llm/quarantined_reader.py`) — strips tags, wraps in `<untrusted_supplier_data>`, enforces max token budget, hashes to audit log | `feature/llm-quarantined-reader` | Completed ✅ |
| P8-3 · Pydantic output schemas (`src/llm/models.py`) — typed response models for every LLM call; rejects free-text responses | `feature/llm-pydantic-output-schemas` | Completed ✅ |
| P8-4 · vLLM confidential contract client — routes EU-regulated contracts to self-hosted vLLM endpoint, never to Bedrock | `feature/llm-vllm-contract-client` | Completed ✅ |
| P8-5 · Mock LLM client for offline tests — returns fixture JSON matching Pydantic schemas; activated by `USE_MOCK_LLM=true` | `feature/llm-mock-client-fixtures` | Completed ✅ |

---

## Phase 9 — LangGraph Agent Workflow

> Depends on: P5-4, P7-1, P7-2, P8-1, and P8-2. Unblocks: Phase 10 (HITL service) and Phase 11 (API routes).
> Merge order: P9-1 first. P9-2, P9-3, and P9-4 in parallel after it. P9-5 after all four. P9-6 last.

| Task | Branch | Status |
|------|--------|--------|
| P9-1 · LangGraph `AgentState` and `StateGraph` skeleton (`src/agents/orchestrator.py`) — defines all nodes and routing edges | `feature/agents-langgraph-skeleton` | Completed ✅ |
| P9-2 · Triage agent node (`src/agents/nodes/triage_agent.py`) — classifies signal type (financial/logistics/geopolitical/news), deterministic routing, no LLM | `feature/agents-triage-node` | Completed ✅ |
| P9-3 · Research agent node (`src/agents/nodes/research_agent.py`) — news scraper tool, SEC EDGAR tool, geopolitical API tool; all text via Quarantined Reader | `feature/agents-research-node` | Completed ✅ |
| P9-4 · Contract agent node (`src/agents/nodes/contract_agent.py`) — extracts payment terms, force majeure clauses via vLLM; confidential docs never leave VPC | `feature/agents-contract-node` | Completed ✅ |
| P9-5 · Risk agent node (`src/agents/nodes/risk_agent.py`) — calls deterministic calculator first, then LLM writes narrative explaining the computed numbers | `feature/agents-risk-node` | Completed ✅ |
| P9-6 · Recommendation agent node (`src/agents/nodes/recommendation_agent.py`) — generates alternative supplier options and spot-buy actions; never auto-approves | `feature/agents-recommendation-node` | Completed ✅ |

---

## Phase 10 — HITL Approval System

> Depends on: P4-2, P4-4, P9-6, and P3-3. Unblocks: Phase 11 (approval API routes).
> Merge order: P10-1 first. P10-2 and P10-3 in parallel after it. P10-4 last.

| Task | Branch | Status |
|------|--------|--------|
| P10-1 · HITL service (`src/services/hitl_service.py`) — issues KMS ECDSA tokens, routes to correct spend tier, enforces 1-hour / 30-minute TTL | `feature/hitl-approval-service` | Completed ✅ |
| P10-2 · Dual-approval enforcer — `DUAL_VP` actions require two independent token signatures before the action node executes | `feature/hitl-dual-approval-enforcer` | Completed ✅ |
| P10-3 · Token replay guard — checks `hitl_approvals.token_hash` unique constraint, logs and alerts on replay attempt | `feature/hitl-token-replay-guard` | Completed ✅ |
| P10-4 · HITL unit tests — valid token, expired token, replayed token, wrong action ID, dual-approval with one missing signature | `feature/hitl-unit-tests` | Completed ✅ |

---

## Phase 11 — FastAPI API Routes

> Depends on: P4-1, P9-1, P10-1, and P3-3. Unblocks: Phase 12 (React frontend).
> Merge order: P11-1 first. P11-2, P11-3, and P11-4 in parallel after it. P11-5 after P11-3. P11-6 last.

| Task | Branch | Status |
|------|--------|--------|
| P11-1 · Alert routes — `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, `POST /api/v1/alerts/{id}/acknowledge` | `feature/api-alert-routes` | Completed ✅ |
| P11-2 · Investigation routes — `POST /api/v1/investigations/start`, `GET /api/v1/investigations/{id}` (async polling) | `feature/api-investigation-routes` | Completed ✅ |
| P11-3 · Approval routes — `GET /api/v1/approvals` (HITL queue), `POST /api/v1/approvals/{id}/sign` (ECDSA token submission) | `feature/api-approval-routes` | Completed ✅ |
| P11-4 · Supplier routes — `GET /api/v1/suppliers/{id}/risk`, `GET /api/v1/suppliers/{id}/graph` (Neptune subgraph) | `feature/api-supplier-routes` | Completed ✅ |
| P11-5 · WebSocket handler — real-time alert push to frontend on new `risk-alerts` Kafka message | `feature/api-websocket-alert-push` | Completed ✅ |
| P11-6 · No-op guard and error standardisation — reject approvals where token already used; all errors return `{error: {code, message, trace_id}}` | `feature/api-error-standardisation` | Completed ✅ |

---

## Phase 12 — React Frontend

> Depends on: P11-1, P11-2, P11-3, and P11-4. Parallel with: nothing inside the phase after P12-1.
> Merge order: P12-1 first (typed API client must exist before components). P12-2 through P12-5 in parallel after it. P12-6 last.

| Task | Branch | Status |
|------|--------|--------|
| P12-1 · Typed API client (`frontend/src/api/`) — axios + Zod schemas for all backend routes; WebSocket hook for live alerts | `feature/frontend-api-client` | Completed ✅ |
| P12-2 · Risk Dashboard page — supplier risk table, severity heat-map, Kafka-driven live alert feed, Zustand store | `feature/frontend-risk-dashboard` | Completed ✅ |
| P12-3 · Investigation Panel — trigger investigation, poll status, display agent narrative + evidence cards | `feature/frontend-investigation-panel` | Completed ✅ |
| P12-4 · HITL Approval Modal — spend tier badge, ECDSA token submission form, dual-approval progress indicator | `feature/frontend-hitl-approval-modal` | Completed ✅ |
| P12-5 · Supplier Graph Visualiser — Neptune subgraph rendered as interactive force-directed graph (D3 or React Flow) | `feature/frontend-supplier-graph-viz` | Completed ✅ |
| P12-6 · Audit Trail Viewer — chronological immutable timeline per alert; role-aware UI (hide approve button for `analyst`) | `feature/frontend-audit-trail-viewer` | Pending ❌ |

---

## Phase 13 — Supplier Seed Data & Golden Datasets

> Depends on: P3-2 and P5-2. Parallel with: Phases 6–12. Does not block any code phase.
> Merge order: P13-1 first. P13-2 and P13-3 in parallel after it. P13-4 last.

| Task | Branch | Status |
|------|--------|--------|
| P13-1 · Supplier seed script (`src/database/seed_dev.py`) — 50 Tier-1 suppliers (10 countries), 200 components, 20 plants, NanoCore scenario loaded | `feature/seed-supplier-data` | Pending ❌ |
| P13-2 · Neptune graph seed — supplier → component → plant edges, tier-chain links, 3 geopolitical risk nodes for NanoCore region | `feature/seed-graph-data` | Pending ❌ |
| P13-3 · Golden dataset (`tests/golden/`) — `nanocore_scenario.json` with exact inputs/expected outputs; 5 edge-case JSON files (zero stock, zero gap, negative gap, dual-approval threshold, single-source dependency) | `feature/seed-golden-datasets` | Pending ❌ |
| P13-4 · OpenSearch vector seed — 500 synthetic contract clauses chunked and embedded into `contracts-v1` index | `feature/seed-opensearch-vectors` | Pending ❌ |

---

## Phase 14 — Unit & Integration Tests

> Depends on: Phase 11 (all API routes done) and Phase 13 (golden datasets). Parallel with: Phase 12.
> Merge order: P14-1 first. P14-2, P14-3, P14-4, and P14-5 in parallel after it. P14-6 last.

| Task | Branch | Status |
|------|--------|--------|
| P14-1 · Risk calculator unit tests — NanoCore golden numbers, zero-stock edge case, zero-consumption guard, negative gap → zero shortage | `feature/tests-unit-risk-calculator` | Pending ❌ |
| P14-2 · HITL token unit tests — valid token, expired TTL, replay detection, wrong action binding, missing second signature | `feature/tests-unit-hitl-tokens` | Pending ❌ |
| P14-3 · Quarantined Reader unit tests — XML injection, markdown injection, Unicode bypass, clean text passthrough | `feature/tests-unit-quarantined-reader` | Pending ❌ |
| P14-4 · Integration test — full investigation flow: Kafka event → triage → risk calculator → HITL gate → approval → audit log | `feature/tests-integration-investigation-flow` | Pending ❌ |
| P14-5 · Integration test — RBAC 403 scenarios: `analyst` calling approve route, `category_manager` signing >$100k action | `feature/tests-integration-rbac` | Pending ❌ |
| P14-6 · Golden dataset pytest suite — `tests/golden/` assertions that fail CI if `days_of_cover != 7.68` or `financial_exposure != 2448105.00` | `feature/tests-golden-dataset-suite` | Pending ❌ |

---

## Phase 15 — Observability

> Depends on: P1-3 and P11-1. Parallel with: Phases 12 and 14. Does not block delivery.
> Merge order: P15-1 and P15-2 in parallel. P15-3 after P15-1. P15-4 after P15-2. P15-5 last.

| Task | Branch | Status |
|------|--------|--------|
| P15-1 · OpenTelemetry setup — `@vercel/otel`-style span instrumentation on all FastAPI routes and agent nodes; `trace_id` propagated to every log line | `feature/observability-otel-setup` | Pending ❌ |
| P15-2 · Langfuse callback integration — `CallbackHandler` on every LangGraph agent run; records tokens used, latency, and cost per investigation | `feature/observability-langfuse-tracing` | Pending ❌ |
| P15-3 · Prometheus metrics export — `apexmotion_investigations_total`, `apexmotion_investigation_duration_seconds`, `apexmotion_llm_tokens_total`, `apexmotion_kafka_consumer_lag`, `apexmotion_hitl_pending_count` | `feature/observability-prometheus-metrics` | Pending ❌ |
| P15-4 · Grafana dashboard JSON — SLO panels: p95 investigation latency ≤ 90s, Kafka lag, HITL queue depth, LLM cost/day | `feature/observability-grafana-dashboard` | Pending ❌ |
| P15-5 · CloudWatch alarms — p95 latency breach, error rate > 1%, Kafka consumer lag > 30s, Neptune query > 2s | `feature/observability-cloudwatch-alarms` | Pending ❌ |

---

## Phase 16 — Infrastructure & Delivery

> Depends on: Phase 14 (all tests pass) and Phase 15.
> Merge order: P16-1 and P16-2 in parallel. P16-3 after both. P16-4 and P16-5 in parallel after P16-3. P16-6 last.

| Task | Branch | Status |
|------|--------|--------|
| P16-1 · `Dockerfile.api` — FastAPI + Uvicorn image (Python 3.12-slim, non-root user, health check) | `feature/docker-api-image` | Pending ❌ |
| P16-2 · `Dockerfile.worker` — Celery worker image for background enrichment and Kafka consumer | `feature/docker-worker-image` | Pending ❌ |
| P16-3 · Terraform modules (`infrastructure/terraform/`) — EKS 1.30, Neptune, Aurora PG 16 Serverless v2, MSK 3-broker, OpenSearch, ElastiCache Redis, S3 Object Lock, KMS | `feature/terraform-aws-infrastructure` | Pending ❌ |
| P16-4 · Kubernetes manifests (`infrastructure/kubernetes/`) — Deployments, Services, KEDA `ScaledObject` for Kafka consumer, HPA for API pods | `feature/kubernetes-manifests-keda` | Pending ❌ |
| P16-5 · GitHub Actions CD pipeline — build → push ECR → `kubectl apply` → blue-green cutover; separate workflows for `staging` and `production` | `feature/cd-pipeline-eks-deploy` | Pending ❌ |
| P16-6 · Deployment hygiene checks — no `.env` committed, no static AWS credentials, S3 Object Lock compliance mode verified, WORM 7-year hold confirmed | `feature/tests-deployment-hygiene` | Pending ❌ |

---

## Dependency Overview

```text
P1  Runtime Skeleton
  └─► P2  Local Dev Environment
        ├─► P3  Persistence Layer (Aurora PG + OpenSearch)
        │     ├─► P4  Identity, Security & HITL Tokens  ──────────────────────┐
        │     ├─► P5  Knowledge Graph (Neptune)          ─────────────────────┤
        │     └─► P6  Kafka Event Ingestion              ─────────────────────┤
        │                                                                     │
        │     P7  Deterministic Risk Engine  ─────────────────────────────────┤
        │     P8  LLM Foundation (LiteLLM + Guardrails) ──────────────────────┤
        │                                                                     │
        │     ┌──────────────────────────────────────────────────────────────-┘
        │     └─► P9  LangGraph Agent Workflow
        │               └─► P10  HITL Approval System
        │                          └─► P11  FastAPI API Routes
        │                                     └─► P12  React Frontend
        │
        ├─► P13  Supplier Seed Data & Golden Datasets (parallel with P6–P12)
        │
        └─► P14  Unit & Integration Tests  (after P11 + P13)
              └─► P15  Observability       (parallel with P12 + P14)
                    └─► P16  Infrastructure & Delivery
```

Phases 4, 5, 6, 7, and 8 all depend on Phase 3 and can be developed in parallel. Phase 9 (agents) is the convergence point — it must wait for Phases 5, 7, and 8. Phase 10 (HITL) waits for Phase 9. Phase 11 (API) waits for Phase 10. Phase 12 (frontend) waits for Phase 11. Phase 13 (seed data) runs in parallel with all code phases from Phase 3 onward. Phase 14 (tests) starts after Phase 11 and Phase 13. Phase 16 (delivery) starts only after Phase 14 passes green.

---

## Map to Delivery Phases

| Task Phases | Delivery Milestone | Target Week | Status |
|-------------|-------------------|-------------|--------|
| P1 + P2 + P3 + P4 (partial) | **POC Foundation** — skeleton, local stack, DB, auth wired | Week 3 | Completed ✅ |
| P4 + P5 + P6 + P7 + P8 | **Risk Engine Ready** — Neptune, Kafka, deterministic calc, LLM gateway | Week 6 | Completed ✅ |
| P9 + P10 + P11 + P13 | **Phase 1 POC** — NanoCore simulation live, HITL demo, all API routes | Week 10 | In Progress 🔄 |
| P12 + P14 + P15 | **MVP Frontend & Test Coverage** — React UI, golden tests green, observability on | Week 16 | Pending ❌ |
| P11 (live Tier-1 connectors) + Production data | **Phase 2 MVP** — Bengaluru, Pune, Munich suppliers live | Week 22 | Pending ❌ |
| P16 | **Phase 3 Production** — EKS full deploy, Mexico, Vietnam, US live | Week 30 | Pending ❌ |

---

## Progress Summary

| Phase | Name | Tasks | Completed |
|-------|------|-------|-----------|
| 1 | Runtime Skeleton | 6 | 6 (100%) ✅ |
| 2 | Local Dev Environment | 5 | 5 (100%) ✅ |
| 3 | Persistence Layer | 5 | 5 (100%) ✅ |
| 4 | Identity, Security & HITL Tokens | 5 | 5 (100%) ✅ |
| 5 | Knowledge Graph (Neptune) | 5 | 5 (100%) ✅ |
| 6 | Kafka Event Ingestion | 4 | 4 (100%) ✅ |
| 7 | Deterministic Risk Engine | 5 | 5 (100%) ✅ |
| 8 | LLM Foundation | 5 | 5 (100%) ✅ |
| 9 | LangGraph Agent Workflow | 6 | 6 (100%) ✅ |
| 10 | HITL Approval System | 4 | 4 (100%) ✅ |
| 11 | FastAPI API Routes | 6 | 6 (100%) ✅ |
| 12 | React Frontend | 6 | 5 (83.3%) 🔄 |
| 13 | Supplier Seed Data & Golden Datasets | 4 | 0 (0%) ❌ |
| 14 | Unit & Integration Tests | 6 | 0 (0%) ❌ |
| 15 | Observability | 5 | 0 (0%) ❌ |
| 16 | Infrastructure & Delivery | 6 | 0 (0%) ❌ |
| **Total** | | **83** | **61 (73.5%)** |
