---
name: cost-report
description: Summarizes token usage, model tier allocation, estimated costs, and context caching efficiency for the current session or repository.
---

# Cost Report Skill (Flash-Lite Tier)

Use this skill to inspect token consumption, context cache hit rates, model routing distribution, and cost savings across subagents.

## Workflow

1. **Execute Token & Cost Helper**:
   - Run the lightweight usage analysis script:
     ```bash
     python3 scripts/antigravity_usage/token_tracker.py
     ```
2. **Review Key Metrics**:
   - Total prompt tokens vs completion tokens.
   - Cached prompt tokens (Gemini Context Caching hit rate).
   - Cost breakdown by tier:
     * `pro`: \$1.25 / 1M prompt (<128k), \$5.00 / 1M completion
     * `flash`: \$0.075 / 1M prompt (<128k), \$0.30 / 1M completion
     * `flash_lite`: \$0.01875 / 1M prompt (<128k), \$0.075 / 1M completion
     * Cache read discount: 75% savings on cached prompt tokens.
3. **Report to User**:
   - Present a concise table summarizing tokens used, cache efficiency, and estimated spend.
