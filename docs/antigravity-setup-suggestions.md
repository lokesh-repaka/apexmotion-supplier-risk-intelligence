
# Antigravity Governance, Model Routing & Parallel Execution Guide

This document summarizes the Google Antigravity (AGY) configuration and operational governance created for the **ApexMotion Supplier Risk Intelligence Platform**.

---

## 1. Governance Architecture Overview

The setup is configured to optimize developer velocity, enforce zero-hallucination guardrails, and minimize Gemini token expenditure through tiered model routing and automatic context caching.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      ANTIGRAVITY GOVERNANCE STACK                     │
├────────────────────────────────────────────────────────────────────────┤
│  Top-Level Rules       GEMINI.md (< 150 lines, static cached prefix)   │
├────────────────────────────────────────────────────────────────────────┤
│  Scoped Path Rules     .agents/rules/ (< 30 lines each)                │
│                        ├── risk-math.md (BR-RULE-001, 100% Python math)│
│                        ├── api-routes.md (Pydantic, Keycloak JWT, trace_id)│
│                        ├── hitl-security.md (KMS ECDSA P-256 tokens)   │
│                        └── tests.md (Offline isolation, golden tests)  │
├────────────────────────────────────────────────────────────────────────┤
│  Agent Tiers           .agents/agents/ & define_subagent               │
│                        ├── Pro Tier: planner, pro-consultant           │
│                        ├── Flash Tier: implementer, code-reviewer, test│
│                        └── Flash-Lite Tier: log-triage, Explore        │
├────────────────────────────────────────────────────────────────────────┤
│  Specialized Skills    .agents/skills/ (plan, implement, review, etc.) │
├────────────────────────────────────────────────────────────────────────┤
│  Lifecycle Hooks       hooks.json & .agents/scripts/pre_commit_gate.sh │
├────────────────────────────────────────────────────────────────────────┤
│  Usage Tracking        scripts/antigravity_usage/token_tracker.py      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Invariant: The Triad of Separation (BR-RULE-001)

Every agent, prompt, and rule strictly upholds the non-negotiable **Triad of Responsibility**:
1. **AI / LLMs**: Unstructured evidence synthesis, news event extraction, and narrative formatting only. **LLMs are strictly forbidden from executing arithmetic calculations.**
2. **Deterministic Python Engine** (`src/services/risk/`): 100% of arithmetic calculations:
   - Days of Cover: $\text{stock} / \text{daily\_rate}$ (NanoCore: 7.68 days)
   - Coverage Gap: $\text{eta} - \text{days\_of\_cover}$ (NanoCore: 1.32 days)
   - Shortage Volume: $\text{gap} \times \text{daily\_rate}$ (NanoCore: 24,420 units)
   - Financial Exposure: $\text{shortage\_volume} \times \text{unit\_cost}$ (NanoCore: \$2,448,105)
   - Line Halt Exposure: €85,000/hr exposure.
   - All currencies stored as `NUMERIC(14,2)` or `Decimal`.
3. **Human Authority (HITL)**: Consequential spend commitments require cryptographically verified AWS KMS ECDSA P-256 tokens:
   - $\le \$25,000$: Category Manager (1x token, 1-hr TTL)
   - $\$25,001 - \$100,000$: Procurement Director (1x token, 1-hr TTL)
   - $> \$100,000$: Dual sign-off (Procurement Director + VP Supply Chain, 2x tokens, 30-min TTL)

---

## 3. Model Tiers & Per-Agent Token Budgets

| Agent | Tier / Model | Max Turns | Return Limit (Hard Cap) | Purpose in ApexMotion |
|---|---|---|---|---|
| **planner** | `pro` | 40 | Relative plan file path only | LangGraph StateGraph, ADRs, phased plans |
| **pro-consultant** | `pro` | 10 | 300 words max | Architecture trade-offs, KMS ECDSA review |
| **implementer** | `flash` | 120 | 150 words summary | FastAPI routes, models, migrations, UI |
| **code-reviewer** | `flash` | 50 | Ranked list (Blocker/Major/Nit) | Pre-commit and PR diff verification |
| **test-engineer** | `flash` | 80 | 100 words digest | Offline unit tests, golden dataset checks |
| **log-triage** | `flash_lite` | 15 | 30 lines max | Error classification for test logs > 50 lines |
| **Explore** | `flash_lite` | 30 | 150 words max | File paths and line numbers only |

### Context Caching Strategy:
- **Prefix Invariance**: System rules (`GEMINI.md`, `.agents/rules/`) and tool declarations remain static across turns.
- **Cache Hit Savings**: Gemini Context Caching yields a **75% discount** on prompt tokens that hit the cached prefix.
- **Cost Minimization**: Heavy reasoning (`pro`) is isolated to planning and architecture queries. Daily code, tests, and reviews run on fast, low-cost `flash`. Verbose logs and search run on ultra-low-cost `flash_lite`.

---

## 4. Pre-Tool Quality & Safety Hook

The hook `.agents/hooks.json` intercepts `run_command` before executing any command containing `git commit`:
- Executes staged linting (`ruff check`) and type checking (`mypy`).
- Fails open if tools are not yet installed in the current environment or if source directories are pending.
- Blocks execution (`decision: "deny"`) if syntax or type errors are detected.
- Verified with `bash -n .agents/scripts/pre_commit_gate.sh`.

---

## 5. Parallel Execution & Swarm Guidelines

To accelerate development safely:
1. **Parallel-Safe Tasks**:
   - Independent backend services (e.g. `src/services/supplier_service.py` vs `src/services/alert_service.py`).
   - Independent unit test files in separate folders.
   - Code reviews across distinct feature branches.
2. **Sequential-Only Tasks**:
   - Database schema migrations (`alembic/migrations/` and `src/database/models.py`).
   - Shared configuration (`src/core/config.py`).
   - Package dependencies (`pyproject.toml`, `package.json`).
3. **Workspace Isolation**:
   - Always run parallel subagents using `workspace: "share"` to share repository files without clobbering uncommitted work.
   - Hard cap: **Maximum 3 concurrent subagents**.

---

## 6. Development Cycle: Ready-to-Paste Snippets

### Full Feature Cycle: `/plan` $\to$ `/implement` $\to$ `/test` $\to$ `/review`

#### Step 1: Architectural Plan (Pro Tier)
```text
/plan Topic: Implement Phase 1 Task P1-4 FastAPI App Skeleton and Request ID Middleware
Constraints: Comply with GEMINI.md, BR-RULE-001, and LLD Section 3.
Write plan to docs/plans/phase-1-fastapi-skeleton.md
```

#### Step 2: Implementation (Flash Tier)
```text
/implement Implement the FastAPI skeleton as specified in docs/plans/phase-1-fastapi-skeleton.md.
Adhere strictly to Pydantic v2 schemas and request tracing.
Verify with unit tests before completing.
```

#### Step 3: Fast Offline Testing (Flash Tier)
```text
/test Run pytest tests/unit/test_api_skeleton.py in offline mode.
Ensure 100% coverage on request_id middleware and error formatting.
```

#### Step 4: Code Quality & Security Review (Flash Tier)
```text
/review Review recent changes in src/api/ against BR-RULE-001 and Keycloak RBAC rules.
Categorize findings by Blocker, Major, and Nit with file:line citations.
```

#### Step 5: Cost & Token Audit (Flash-Lite Tier)
```text
/cost-report Run token_tracker.py to inspect session token expenditure, model distribution, and context cache hits.
```

---

## 7. Remaining Environment Placeholders & Next Steps

1. `<TODO: cd frontend && npm test>`: Add frontend unit test command once Next.js / Vite testing harness (Vitest/Jest) is bootstrapped in `frontend/package.json`.
2. As feature branches are implemented according to `TASKS.md`, ensure all new migrations and services follow `.agents/rules/`.
