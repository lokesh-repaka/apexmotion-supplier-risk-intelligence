---
name: test
description: Triggers the Flash-tier test-engineer subagent on scoped test files, enforcing offline isolation, 100% coverage on critical modules, and golden scenario checks.
---

# Test Skill (Flash Tier)

Use this skill to execute unit tests, golden dataset verification, or coverage checks.

## Workflow

1. **Scope Test Target**:
   - Determine whether running unit tests (`tests/unit/`), golden scenarios (`tests/golden/`), or full coverage.
2. **Invoke Test-Engineer Subagent**:
   - Agent Type: `test-engineer`
   - Model: `flash`
   - Role: `QA & Test Automation Engineer`
   - Prompt:
     ```
     Execute test suite: <test paths or scope>.
     Ensure tests run in complete offline isolation.
     Verify tests/golden/nanocore_scenario.json matches expected numbers exactly.
     If failures occur, diagnose the root cause with targeted fixes.
     Return strictly a digest under 100 words: pass count, failures with stack trace, and execution time.
     ```
3. **Handle Large Failures**:
   - If test output exceeds 50 lines, delegate output to `log-triage` (Flash-Lite) for rapid 30-line diagnostic extraction.
