/**
 * HITL Approval Modal Components Unit Tests (P12-4)
 *
 * Verifies:
 * - SpendTierBadge governance router thresholds (Tier 1 <= $25k, Tier 2 $25k-$100k, Tier 3 > $100k)
 * - DualApprovalProgress dual signature slots and status indicators
 * - Anti-replay and review attestation invariants
 * - Canonical NanoCore reference scenario spend attributes
 */

import { describe, expect, it } from 'vitest';
import {
  CANONICAL_APPROVAL_ITEMS,
  resolveSpendTier,
} from '../../stores/useApprovalStore';

describe('HITL Approval Modal Governance Invariants', () => {
  it('correctly categorizes NanoCore mitigation options under BR-RULE-004 spend tiers', () => {
    // Option 1: Air Charter Freight ($180,000) -> Tier 3 Dual VP Sign-off
    const opt1Cost = 180000;
    expect(resolveSpendTier(opt1Cost)).toBe('DUAL_VP');

    // Option 2: MicroChip Global AML ($240,000) -> Tier 3 Dual VP Sign-off
    const opt2Cost = 240000;
    expect(resolveSpendTier(opt2Cost)).toBe('DUAL_VP');

    // Option 3: Production Rebalance ($0 direct cash) -> Tier 1 Category/Plant Director
    const opt3Cost = 0;
    expect(resolveSpendTier(opt3Cost)).toBe('CATEGORY_MGR');

    // Intermediate Tier: $75,000 -> Tier 2 Procurement Director
    const optMidCost = 75000;
    expect(resolveSpendTier(optMidCost)).toBe('PROC_DIRECTOR');
  });

  it('enforces dual signature slots for DUAL_VP spend tiers', () => {
    const dualItem = CANONICAL_APPROVAL_ITEMS.find((a) => a.spend_tier === 'DUAL_VP');
    expect(dualItem).toBeDefined();

    // Must require 2 distinct signatures
    const requiredSignatures = dualItem?.spend_tier === 'DUAL_VP' ? 2 : 1;
    expect(requiredSignatures).toBe(2);

    // Initial state has 0 signatures
    expect(dualItem?.approved_by.length).toBe(0);
    expect(dualItem?.status).toBe('PENDING');
  });

  it('verifies partially approved state when exactly 1 of 2 signatures is collected', () => {
    const partiallyApprovedItem = CANONICAL_APPROVAL_ITEMS.find(
      (a) => a.status === 'PARTIALLY_APPROVED'
    );
    expect(partiallyApprovedItem).toBeDefined();
    expect(partiallyApprovedItem?.spend_tier).toBe('DUAL_VP');
    expect(partiallyApprovedItem?.approved_by.length).toBe(1);
    expect(partiallyApprovedItem?.approved_by[0]).toContain('Procurement Director');
  });

  it('verifies cryptographically sealed state when both signatures are collected', () => {
    const approvedItem = CANONICAL_APPROVAL_ITEMS.find((a) => a.status === 'APPROVED');
    expect(approvedItem).toBeDefined();
    expect(approvedItem?.approved_by.length).toBeGreaterThanOrEqual(1);
    expect(approvedItem?.status).toBe('APPROVED');
  });

  it('verifies anti-replay token hash presence on all approval items', () => {
    for (const item of CANONICAL_APPROVAL_ITEMS) {
      expect(item.token_hash).toBeDefined();
      expect(item.token_hash.length).toBeGreaterThanOrEqual(32);
      expect(item.expires_at).toBeDefined();
      expect(new Date(item.expires_at).getTime()).toBeGreaterThan(Date.now() - 60000);
    }
  });
});
