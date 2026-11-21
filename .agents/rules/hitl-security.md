---
trigger: glob
globs: **/src/core/hitl_tokens.py, **/src/services/hitl_service.py
---
# HITL Security & Spend Authority Rules

- **ECDSA Verification**: All spend actions require KMS-signed ECDSA P-256 tokens verified against AWS KMS.
- **Strict Spend Thresholds**:
  - `≤ $25,000`: Category Manager approval (1x token, 1-hour TTL).
  - `$25,001 - $100,000`: Procurement Director approval (1x token, 1-hour TTL).
  - `> $100,000`: Dual sign-off required (Procurement Director + VP Supply Chain, 2x tokens, 30-min TTL).
- **Anti-Replay Protection**: Token hashes are unique. Token reuse is blocked and alerted as a security event.
- **Zero LLM Authority**: LLMs can NEVER mint, sign, or approve HITL tokens.
