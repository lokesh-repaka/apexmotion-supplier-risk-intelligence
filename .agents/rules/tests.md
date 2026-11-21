---
trigger: glob
globs: **/tests/**
---
# Testing Standards & Isolation

- **Offline Isolation**: Unit tests (`tests/unit/`) must pass with zero network, zero AWS, and zero live LLM calls.
- **Fixtures & Mocking**: Use pytest fixtures with `unittest.mock` or LocalStack stubs for external dependencies.
- **Coverage Mandate**: 100% coverage on `risk/calculator.py`, `core/hitl_tokens.py`, and `guardrails/input_sanitizer.py`.
- **Golden Scenario**: `tests/golden/nanocore_scenario.json` must match exact outputs; any difference fails build.
- **Concise Reporting**: Keep assertion output clean and bounded for automated log triage.
