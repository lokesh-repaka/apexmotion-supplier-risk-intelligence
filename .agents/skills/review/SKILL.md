---
name: review
description: Runs the Flash-tier code-reviewer subagent on git diffs or modified files to perform security, architectural, and quality audits.
---

# Code Review Skill (Flash Tier)

Use this skill before merging, committing, or after implementation to verify code quality and compliance with ApexMotion invariants.

## Workflow

1. **Identify Changes**:
   - Collect current `git diff` or list of modified source files.
2. **Invoke Code-Reviewer Subagent**:
   - Agent Type: `code-reviewer`
   - Model: `flash`
   - Role: `Lead Code Quality Reviewer`
   - Prompt:
     ```
     Review the recent changes against ApexMotion architectural standards:
     1. Triad of Responsibility (BR-RULE-001): Zero arithmetic performed by LLMs.
     2. HITL Security: KMS ECDSA P-256 token verification and anti-replay checks.
     3. API Security: Keycloak JWT validation and require_role() enforcement.
     4. Data Integrity: NUMERIC(14,2) or Decimal for currency; append-only audit logs.
     Return ONLY a ranked findings list categorized by Severity: [Blocker], [Major], [Nit].
     Include file:line citations and exact fixes. No conversational preamble.
     ```
3. **Report Output**:
   - Present the severity-ranked findings directly to the developer.
