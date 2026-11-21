---
name: implement
description: Delegates approved plans or development tasks to the Flash-tier implementer subagent for rapid, cost-effective execution.
---

# Implement Skill (Flash Tier)

Use this skill to execute coding, schema design, API endpoint creation, or migration tasks after a plan has been reviewed or confirmed.

## Workflow

1. **Verify Plan & Constraints**:
   - Check `docs/plans/<topic>.md` or user request.
   - Reiterate BR-RULE-001: 100% of arithmetic in deterministic Python; zero LLM math.
2. **Invoke Implementer Subagent**:
   - Agent Type: `implementer`
   - Model: `flash`
   - Role: `Full-Stack Software Engineer`
   - Prompt:
     ```
     Implement the tasks specified in: <plan or task description>.
     Adhere strictly to project rules in GEMINI.md.
     Run unit tests to verify implementation before returning.
     Return strictly a summary under 150 words: changed files, test status, and open issues.
     ```
3. **Review Digest**:
   - Verify that the subagent's summary stays under 150 words.
   - Proceed to testing or code review skill.
