---
name: consult-pro
description: Prompts the Pro-tier pro-consultant subagent for high-complexity architectural verification, cryptographic design, or LangGraph state machine decisions.
---

# Consult Pro Skill (Pro Tier)

Use this skill when facing architectural ambiguities, trade-offs, state machine transitions, or cryptographic security dilemmas that require deep reasoning.

## Workflow

1. **Frame Technical Question**:
   - Synthesize the exact architectural question, trade-offs, and constraints into a concise prompt.
2. **Invoke Pro-Consultant Subagent**:
   - Agent Type: `pro-consultant`
   - Model: `pro`
   - Role: `Principal Architecture Consultant`
   - Prompt:
     ```
     Consultation Request: <architectural query>.
     Context: ApexMotion Supplier Risk Intelligence Platform.
     Constraints: BR-RULE-001 (Deterministic math), AWS KMS ECDSA P-256 tokens, LangGraph StateGraph.
     Provide a direct, authoritative, and concise architectural answer with exact technical specifications.
     Do not include boilerplate or pleasantries. Return strictly within 300 words.
     ```
3. **Incorporate Findings**:
   - Incorporate the consultant's decision directly into architecture documentation or ADRs.
