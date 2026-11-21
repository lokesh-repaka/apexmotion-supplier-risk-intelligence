You have access to the project's authoritative documentation: `TASKS.md`, `CLAUDE.md`, `GEMINI.md`, `.agents/rules/`, and architecture specifications in `docs/` (`HLD_*.md`, `LLD_*.md`, `PRD_*.md`, `BRD_*.md`, `FRD_*.md`).

Go ahead and complete **P1-3 · Structured JSON logging (`src/core/logging.py`)**, as defined in `TASKS.md`.

---

### Dual-Persona Execution Workflow (Author + Senior Code Reviewer)

This workflow incorporates the official **roadmap.sh Code Review Standard** and **ApexMotion Antigravity Governance**, enforcing a strict separation between **Author (Implementation)** and **Reviewer (Architectural Quality & Security Gate)** before any code is merged.

---

### 1. Requirements & Context Verification (Before Development)
* **Definition of Done (DoD):** Review the task definition, branch name, and acceptance criteria in `TASKS.md` and `CLAUDE.md`.
* **Layering Invariants (CLAUDE.md Section 5.2):**
  - **Frontend (`frontend/src/`):** React 18/TypeScript/Tailwind components and HITL modals. *Must not contain business logic or call AWS directly.*
  - **API (`src/api/`):** FastAPI routes, Pydantic v2 schemas, Keycloak RBAC, and `request_id` middleware. *Must not contain risk calculation logic.*
  - **Agent Orchestrator (`src/agents/`):** LangGraph StateGraph, agent nodes, and tool definitions. *Must not perform math or query databases directly.*
  - **Risk Engine (`src/services/risk/`):** Deterministic Python arithmetic (Days of Cover, Shortage Volume, Financial Exposure). *Strictly zero LLM calls.*
  - **LLM Gateway (`src/llm/`):** LiteLLM client, prompt templates, and Quarantined Reader. *Must not execute business rules or write to DB.*
  - **Data Layer (`src/database/`, `src/graph/`):** Aurora PG (SQLAlchemy async), OpenSearch vector search, Neptune OpenCypher queries.
  - **Core & Security (`src/core/`):** Settings, Keycloak JWT auth, KMS ECDSA P-256 HITL tokens, and append-only audit logging.
* **Pre-condition Check:** Ensure all predecessor tasks listed in `TASKS.md` are marked `Completed ✅`.
* **Branching:** Create and switch to the assigned feature branch from `TASKS.md` off `development`:
  ```bash
  git checkout development && git pull origin development
  git checkout -b feature/<branch-name>
  ```

---

### 2. Test-Driven Development (TDD) (Author Phase)
* **Failing Test First:** Write comprehensive unit or integration test cases under `tests/` before writing production code.
* **Strict Offline Isolation:** All unit tests must execute with zero external network or AWS calls using the local mock flags:
  ```bash
  USE_LOCALSTACK=true USE_MOCK_LLM=true USE_LOCAL_KAFKA=true pytest tests/<target_path> -v
  ```
* **Confirm Expected Failure:** Run tests first to verify they fail for the intended reason:
  ```bash
  pytest tests/<target_path> -v
  ```
* **The Triad of Responsibility (BR-RULE-001):**
  - **Pure Python Math:** Days of Cover (`stock / daily_rate`), Shortage Gap (`eta - cover`), Shortage Volume (`gap * daily_rate`), and Financial Exposure (`shortage * unit_cost`) must run in deterministic Python services. **LLMs are strictly forbidden from executing arithmetic.**
  - **Monetary Precision:** Always use `Decimal` or `NUMERIC(14,2)` — never native floating-point types for currency or inventory costs.
  - **Golden Verification:** Verify that the canonical **NanoCore Reference Scenario** reproduces exact values (`7.68` days cover, `1.32` days gap, `24,420` units shortage, `$2,448,105.00` exposure).
* **Verify Green:** Re-run pytest to verify all tests pass:
  ```bash
  pytest tests/<target_path> -v
  ```

---

### 3. Post-Development Self-Review (Author Phase)
*Before handing off code for review, the Author must perform self-inspection on the git diff:*
* **Diff Audit:** Run `git diff` to verify every change is minimal, intentional, and scoped strictly to the task.
* **Hygiene Check:**
  - Confirm zero dead code and no leftover `print()` statements (use `src.core.logging` with `trace_id`).
  - Confirm zero hardcoded secrets or credentials (use `src.core.config.get_settings()`).
  - Confirm no unquarantined external text is fed to LLMs (all untrusted supplier data must pass through `QuarantinedReader`).
* **Automated Code Quality:** Execute project linters and type checkers:
  ```bash
  ruff check src/ tests/
  ruff format --check src/ tests/
  mypy src/
  ```
  *(If frontend code was modified: `cd frontend && npm run lint && npm run type-check`)*

---

### 4. Rigorous Code Review & Adversarial Audit (Reviewer Persona)
*Adopt the persona of an objective **Senior Staff Software Architect & Lead Security Reviewer** for ApexMotion. Conduct a structured audit of the git diff using the roadmap.sh review criteria:*

#### A. Review Dimensions:
1. **The Triad of Responsibility & Architectural Integrity:**
   - **Zero LLM Math:** Did any prompt or agent node attempt to compute financial risk, days of cover, or shortage volume? *(Critical Blocker)*
   - **Layering Purity:** Did route handlers leak into service math? Did LangGraph nodes attempt direct database I/O? Did `src/core/` import `agents` or `llm`?
   - **Audit Invariant:** Is `audit_logs` strictly append-only? *(Zero `UPDATE` or `DELETE` statements allowed).*
2. **Logic, Precision & Canonical Reference Invariants:**
   - Are monetary values stored and calculated using `Decimal` / `NUMERIC(14,2)`?
   - Are edge cases handled: zero inventory, zero consumption, negative delivery gap, supplier single-source dependency?
   - Does `tests/golden/nanocore_scenario.json` match with 100% precision?
3. **Security, HITL & Penetration Audit (CWE / Threat Modeling):**
   - **Prompt Injection Defense:** Is untrusted supplier input sanitized and wrapped in `<untrusted_supplier_data>...</untrusted_supplier_data>` delimiters before LLM synthesis?
   - **HITL Cryptographic Gates:** Are consequential spend actions gated by AWS KMS ECDSA P-256 tokens?
     - Spend $\le$ $25,000: Category Manager (1x token, 1-hr TTL).
     - Spend $25,001 – $100,000: Procurement Director (1x token, 1-hr TTL).
     - Spend > $100,000: Dual sign-off (Procurement Director + VP Supply Chain, 2x tokens, 30-min TTL).
   - **Anti-Replay Protection:** Does `hitl_approvals.token_hash` enforce uniqueness to prevent token replay attacks?
   - **RBAC:** Are API routes protected by Keycloak JWT validation and `require_role()` guards?
4. **Test Quality & Coverage:**
   - 100% coverage on `src/services/risk/calculator.py`, `src/core/hitl_tokens.py`, and `src/guardrails/input_sanitizer.py`.
   - $\ge 80\%$ coverage across all other `src/` modules.
   - Zero live cloud/network dependencies in unit tests.

#### B. Review Output Format:
Emit a structured review scorecard with prioritized, actionable feedback:
* **`[BLOCKING]`**: Triad violations (LLM math), security vulnerabilities (KMS replay, missing Keycloak RBAC, prompt injection), float currency, or missing tests. *(Must be resolved before merge)*
* **`[WARNING]`**: Sub-optimal Cypher/SQL queries, missing trace_id propagation, or high cognitive complexity. *(Must be addressed or justified)*
* **`[NIT]`**: Minor docstring refinements, typing hints, or style polish. *(Non-blocking)*

---

### 5. Review Remediation & Verification Loop (Author Phase)
* **Address Findings:** Resolve all `[BLOCKING]` and `[WARNING]` items raised in the review scorecard.
* **Explain Fixes:** Document the specific code adjustments made for each item.
* **Zero Regressions:** Re-verify the full test suite and linters:
  ```bash
  ruff check src/ tests/
  mypy src/
  pytest tests/unit/ -v
  pytest tests/golden/ -v
  pytest --cov=src --cov-fail-under=80
  ```

---

### 6. Housekeeping & Tracking
* **Task Tracker:** In `TASKS.md`, mark the task as `Completed ✅` and update the phase progress.
* **Cost & Token Audit:** Run the token governance tracker to verify context caching efficiency and subagent spend:
  ```bash
  python3 scripts/antigravity_usage/token_tracker.py
  ```
* **Git Hygiene:** Verify `.gitignore` ignores all local caches (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.venv/`).

---

### 7. GitHub PR & Terminal Merge (`gh`)
* **Atomic Commit:** Stage and commit changes using conventional commits (the Antigravity pre-commit hook will auto-validate with `ruff` and `mypy`):
  ```bash
  git add . && git commit -m "feat(<scope>): <concise description>"
  git push origin feature/<branch-name>
  ```
* **Create PR:** Open a Pull Request targeting `base: development` with the review scorecard included in the description:
  ```bash
  gh pr create --base development --title "feat(<scope>): <title>" --body "<summary_and_review_scorecard>"
  ```
* **Verify CI Status:** Ensure all GitHub Actions checks pass:
  ```bash
  gh pr checks
  ```
* **Terminal Merge:** Merge cleanly and delete the remote feature branch:
  ```bash
  gh pr merge --merge --delete-branch
  ```
* **Local Sync:** Switch back to `development` and pull the latest state:
  ```bash
  git checkout development && git pull origin development
  ```