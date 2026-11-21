---
trigger: glob
globs: **/src/services/risk/**
---
# Deterministic Risk Math Rules (BR-RULE-001)

- **Zero LLM Math**: LLMs must NEVER perform risk, inventory, or financial calculations.
- **Pure Python/NumPy**: 100% of arithmetic (Days of Cover, Shortage Gap, Exposure) must be in Python services.
- **Canonical NanoCore Golden Metrics**:
  - `days_of_cover = current_stock / daily_consumption_rate` (7.68 days)
  - `gap_days = eta_days - days_of_cover` (1.32 days)
  - `shortage_volume = gap_days * daily_rate` (24,420 units)
  - `financial_exposure = shortage_volume * unit_cost` ($2,448,105)
- **Precision**: Use exact numeric types (`Decimal` / `NUMERIC(14,2)`). Never use float for money.
- **Audit Hash Chaining**: Every calculation output must generate a SHA-256 state hash for audit logs.
- **Test Mandate**: 100% unit test coverage required. Must pass `tests/golden/nanocore_scenario.json`.
