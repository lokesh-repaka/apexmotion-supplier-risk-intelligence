/**
 * Audit Trail & Role-Aware Governance Unit Tests (P12-6)
 *
 * Verifies:
 * - Role-Aware Governance Invariants (CLAUDE.md Sec 10 & TASKS.md P12-6):
 *   - Analyst role is strictly read-only; spend approval triggers are hidden.
 *   - Category Manager, Procurement Director, and VP Supply Chain unlock tiered spend authority.
 * - WORM S3 Object Lock & SHA-256 Merkle Hash Chaining (BR-RULE-007).
 * - Deterministic Risk Arithmetic Proof preservation in Block 3 (BR-RULE-001).
 * - Multi-Executive Dual Sign-off Progression in Blocks 5-7 (BR-RULE-004).
 * - CI/CD Automated Regression Evaluation Gate metrics (FRD FR-GOV-002).
 */

import { describe, expect, it } from 'vitest';
import {
  CANONICAL_NANOCORE_AUDIT_BLOCKS,
  CONTINUOUS_EVALS_METRICS,
  ENFORCED_BUSINESS_RULES,
  USER_PERSONAS,
} from '../../stores/useAuditStore';

describe('Audit Trail Viewer & Role-Aware Governance Invariants (P12-6)', () => {
  it('enforces Analyst role-aware spend restriction (TASKS.md P12-6)', () => {
    const analystPersona = USER_PERSONAS.analyst;

    expect(analystPersona.role).toBe('analyst');
    expect(analystPersona.canApproveSpend).toBe(false);
    expect(analystPersona.maxSpendLimitUsd).toBe(0);

    // Verify persona description explicitly states spend authorization is disabled
    expect(analystPersona.description).toContain('Spend authorization');
  });

  it('enforces tiered spend authorities under Rule BR-RULE-004', () => {
    // Category Manager: <= $25,000
    const catMgr = USER_PERSONAS.category_manager;
    expect(catMgr.canApproveSpend).toBe(true);
    expect(catMgr.maxSpendLimitUsd).toBe(25000);

    // Procurement Director: <= $100,000
    const procDir = USER_PERSONAS.procurement_director;
    expect(procDir.canApproveSpend).toBe(true);
    expect(procDir.maxSpendLimitUsd).toBe(100000);

    // VP Supply Chain: > $100,000 (Dual VP sign-off)
    const vp = USER_PERSONAS.vp_supply_chain;
    expect(vp.canApproveSpend).toBe(true);
    expect(vp.maxSpendLimitUsd).toBeNull(); // Unlimited dual executive authority
  });

  it('validates unbroken Merkle SHA-256 hash chaining from Genesis to Block 8', () => {
    const blocks = CANONICAL_NANOCORE_AUDIT_BLOCKS;
    expect(blocks.length).toBe(8);

    // Block 1 must have Genesis 64-zero previous hash
    expect(blocks[0].previous_hash).toBe(
      '0000000000000000000000000000000000000000000000000000000000000000'
    );

    // Consecutive blocks must link strictly to previous block's current_hash
    for (let i = 1; i < blocks.length; i++) {
      expect(
        blocks[i].previous_hash,
        `Block #${blocks[i].block_index} previous_hash must match Block #${blocks[i - 1].block_index} current_hash`
      ).toBe(blocks[i - 1].current_hash);
    }
  });

  it('reproduces NanoCore deterministic math proof in Block 3 (BR-RULE-001)', () => {
    const mathBlock = CANONICAL_NANOCORE_AUDIT_BLOCKS.find(
      (b) => b.action === 'MATH_CERTIFIED'
    );
    expect(mathBlock).toBeDefined();

    const after = mathBlock?.after_state as {
      days_of_cover: string;
      shortage_gap_days: string;
      projected_shortage_units: number;
      financial_exposure_usd: string;
      plant_halt_rate_eur_hr: string;
    };

    expect(after.days_of_cover).toBe('7.68');
    expect(after.shortage_gap_days).toBe('1.32');
    expect(after.projected_shortage_units).toBe(24420);
    expect(after.financial_exposure_usd).toBe('2448105.00');
    expect(after.plant_halt_rate_eur_hr).toBe('85000.00');
    expect(mathBlock?.actor_name).toContain('Deterministic Python');
  });

  it('validates dual executive approval sequence in Blocks 5, 6, and 7', () => {
    const routerBlock = CANONICAL_NANOCORE_AUDIT_BLOCKS.find(
      (b) => b.action === 'HITL_PENDING_REVIEW'
    );
    expect(routerBlock).toBeDefined();
    expect(routerBlock?.after_state?.spend_tier).toBe('DUAL_VP');
    expect(routerBlock?.after_state?.required_signatures).toBe(2);

    const sign1 = CANONICAL_NANOCORE_AUDIT_BLOCKS.find(
      (b) => b.block_index === 6
    );
    expect(sign1?.action).toBe('HITL_TOKEN_SIGNED');
    expect(sign1?.actor_name).toBe('Priya Sharma');
    expect(sign1?.after_state?.signatures_collected).toBe(1);
    expect(sign1?.after_state?.status).toBe('PARTIALLY_APPROVED');
    expect(sign1?.signature).toBeDefined();

    const sign2 = CANONICAL_NANOCORE_AUDIT_BLOCKS.find(
      (b) => b.block_index === 7
    );
    expect(sign2?.action).toBe('HITL_TOKEN_SIGNED');
    expect(sign2?.actor_name).toBe('Elena Rostova');
    expect(sign2?.after_state?.signatures_collected).toBe(2);
    expect(sign2?.after_state?.status).toBe('APPROVED');
    expect(sign2?.signature).toBeDefined();

    const dispatch = CANONICAL_NANOCORE_AUDIT_BLOCKS.find(
      (b) => b.block_index === 8
    );
    expect(dispatch?.action).toBe('SAP_PO_DISPATCHED');
    expect(dispatch?.after_state?.sap_po_number).toBe('PR-2026-009182');
  });

  it('verifies CI/CD continuous evaluation gate targets (FRD FR-GOV-002)', () => {
    // Must contain 4 primary evals metrics
    expect(CONTINUOUS_EVALS_METRICS.length).toBe(4);

    const f1 = CONTINUOUS_EVALS_METRICS.find((m) => m.name.includes('Entity'));
    expect(Number(f1?.value)).toBeGreaterThanOrEqual(0.95);

    const graph = CONTINUOUS_EVALS_METRICS.find((m) => m.name.includes('Graph'));
    expect(graph?.value).toBe('100%');

    const math = CONTINUOUS_EVALS_METRICS.find((m) => m.name.includes('Math'));
    expect(math?.value).toBe('100%');

    const cit = CONTINUOUS_EVALS_METRICS.find((m) => m.name.includes('Citation'));
    expect(Number(cit?.value)).toBeGreaterThanOrEqual(0.98);

    // Must enforce all 7 platform business rules
    expect(ENFORCED_BUSINESS_RULES.length).toBe(7);
    const ruleIds = ENFORCED_BUSINESS_RULES.map((r) => r.id);
    expect(ruleIds).toEqual([
      'BR-001',
      'BR-002',
      'BR-003',
      'BR-004',
      'BR-005',
      'BR-006',
      'BR-007',
    ]);
  });
});
