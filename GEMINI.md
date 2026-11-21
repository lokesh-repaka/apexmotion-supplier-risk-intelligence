# GEMINI.md — ApexMotion Antigravity Governance & Project Rules

## 1. Project Overview & Core Stack
ApexMotion Supplier Risk Intelligence Platform:
- **Backend**: FastAPI (Python 3.12+), Pydantic v2, uvicorn
- **Agent Orchestrator**: LangGraph multi-agent workflows
- **Persistence**: Amazon Aurora PostgreSQL (SQLAlchemy async), Amazon Neptune (OpenCypher), Redis Cache
- **Streaming & Search**: Amazon MSK (Kafka), Amazon OpenSearch (vector search)
- **Frontend**: Next.js 14 / React 18, TypeScript, Tailwind CSS
- **Security**: Keycloak SSO (OIDC/JWT), AWS KMS (ECDSA P-256 HITL tokens)

## 2. Standard Development & Verification Commands
- **Unit Tests**: `pytest tests/unit/ -v` (offline, zero external I/O)
- **Integration Tests**: `pytest tests/integration/ -v` (Testcontainers/LocalStack)
- **Golden Tests**: `pytest tests/golden/ -v` (NanoCore reference scenario)
- **Coverage**: `pytest --cov=src --cov-fail-under=80`
- **Linting**: `ruff check src/ tests/` && `ruff format --check src/ tests/`
- **Type Checking**: `mypy src/`
- **Backend Dev**: `uvicorn src.api.main:app --reload --port 8000`
- **Frontend Dev**: `cd frontend && npm run dev`
- **Frontend Lint**: `cd frontend && npm run lint`
- **Frontend Tests**: `<TODO: cd frontend && npm test>`

## 3. The Triad of Separation Guardrail (BR-RULE-001)
Strict architectural separation between probabilistic AI, deterministic compute, and human authority:
1. **AI / LLMs**: Unstructured evidence synthesis, news extraction, and narrative formatting only.
   - **STRICT PROHIBITION**: LLMs are strictly forbidden from performing any arithmetic.
2. **Deterministic Python Engine** (`src/services/risk/`): 100% of arithmetic calculations:
   - Days of Cover: `days_of_cover = current_stock / daily_consumption_rate` (NanoCore: 7.68 days)
   - Coverage Gap: `gap_days = eta_days - days_of_cover` (NanoCore: 1.32 days)
   - Shortage Volume: `shortage_volume = gap_days * daily_rate` (NanoCore: 24,420 units)
   - Financial Exposure: `shortage_volume * unit_cost` (NanoCore: $2,448,105)
   - Line Halt Exposure: €85,000/hr factory halt impact.
   - All monetary values must use `Decimal` or `NUMERIC(14,2)` — never standard float.
3. **Human Authority (HITL)**: Cryptographically verified spend gates:
   - Spend $\le$ $25,000: Category Manager approval (1x ECDSA token, 1-hr TTL).
   - Spend $25,001 – $100,000: Procurement Director approval (1x ECDSA token, 1-hr TTL).
   - Spend > $100,000: Dual sign-off (Procurement Director + VP Supply Chain, 2x tokens, 30-min TTL).

## 4. Antigravity Model Routing & Cost Governance
- **Default Session Model**: `flash` (fast, cost-effective daily engineering).
- **Heavy Reasoning Tier (`pro`)**: Reserved strictly for architectural design, LangGraph StateGraph schema, ADRs, cryptographic token security verification (`planner`, `pro-consultant`).
- **Standard Engineering Tier (`flash`)**: API endpoints, Pydantic schemas, SQLAlchemy models, Alembic migrations, frontend components, unit tests, code reviews (`implementer`, `code-reviewer`, `test-engineer`).
- **Lightweight Utility Tier (`flash_lite`)**: Codebase search/grep, log triage, diff scanning, formatting (`log-triage`, `Explore`).
- **Output Governance**: Use `log-triage` for test or build outputs exceeding 50 lines.
- **Session Focus**: Keep turns scoped to a single task to maximize context cache reuse.

## 5. Parallel Execution & Workspace Safety
- **Safe Parallel Tasks**: Independent backend services (`src/services/`), isolated unit tests, parallel code review.
- **Sequential Only Tasks**: Database schema migrations (`alembic/`), `src/core/config.py`, package dependencies (`pyproject.toml`, `package.json`).
- **Isolation Mode**: Always use `workspace: "share"` (shared worktree) for parallel agents.
- **Concurrency Cap**: Maximum 3 concurrent agents in swarm or background.

## 6. Protected Files & Security Boundaries
- **Strictly Protected (Read-Only)**: `CLAUDE.md`, `TASKS.md`, `docs/**`, `BRD_*.md`, `PRD_*.md`, `HLD_*.md`, `LLD_*.md`, `FRD_*.md`, `demo/mockup_apexmotion_risk.html`. Never edit or overwrite.
- **Denied Secrets**: `.env*`, `*.pem`, `*.key`, `*credentials*.json`, `secrets/**`. Never commit or expose secrets.
