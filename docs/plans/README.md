# ApexMotion Architectural & Implementation Plans

This directory stores architectural plans, LangGraph workflow designs, and phased implementation roadmaps produced by the Pro-tier `planner` subagent or via the `/plan` skill.

## Plan File Naming Convention
- `docs/plans/<topic-kebab-case>.md` (e.g. `docs/plans/phase-1-runtime-skeleton.md`)

## Plan Structure
1. **Goal & Scope**: Business requirement alignment and target modules.
2. **Invariants**: Explicit compliance with the Triad of Responsibility (BR-RULE-001, deterministic Python math only).
3. **Phased Execution**: Step-by-step technical implementation with file paths and schemas.
4. **Verification & Tests**: Offline unit tests, golden dataset assertions, and coverage gates.
