---
name: plan
description: Invokes the Pro-tier planner subagent to draft an architectural and phased implementation plan in docs/plans/<topic>.md.
---

# Plan Skill (Pro Tier)

Use this skill when the user asks to plan a feature, architectural change, LangGraph workflow, or integration task.

## Workflow

1. **Clarify Scope**: Identify the target topic, technical boundaries, and requirements from `CLAUDE.md` and `GEMINI.md`.
2. **Invoke Planner Subagent**:
   - Agent Type: `planner`
   - Model: `pro`
   - Role: `Architectural Planner`
   - Prompt:
     ```
     Create a comprehensive, phased implementation plan for: <topic>.
     Ensure compliance with BR-RULE-001 (Zero LLM math, deterministic Python only),
     Keycloak RBAC, and AWS KMS ECDSA P-256 token validation.
     Write the complete plan to docs/plans/<topic>.md.
     Return ONLY the relative path to the plan file.
     ```
3. **Completion**:
   - Receive the relative path from the subagent.
   - Present the plan location to the user and request review before implementation.
