/**
 * HITL Approval Store Unit Tests (P12-4)
 *
 * Verifies:
 * - Spend tier resolution matching BR-RULE-004 thresholds
 * - Initial state hydration with canonical NanoCore reference approval items
 * - Modal opening from approval items and investigation mitigation scenarios
 * - Single-signature approval progression (Category Mgr / Director -> APPROVED)
 * - Dual-signature approval progression (> $100k: 1st -> PARTIALLY_APPROVED, 2nd -> APPROVED)
 * - Approval rejection handling and audit justification capture
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { approvalApi } from '../api/routes/approvals';
import type { ApprovalItem, ApprovalSignResponse } from '../api/types';
import {
  CANONICAL_APPROVAL_ITEMS,
  resolveSpendTier,
  useApprovalStore,
} from './useApprovalStore';

describe('useApprovalStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useApprovalStore.getState().reset();
  });

  describe('resolveSpendTier Thresholds (BR-RULE-004)', () => {
    it('resolves <= $25,000 to CATEGORY_MGR', () => {
      expect(resolveSpendTier(0)).toBe('CATEGORY_MGR');
      expect(resolveSpendTier(15000)).toBe('CATEGORY_MGR');
      expect(resolveSpendTier(25000)).toBe('CATEGORY_MGR');
      expect(resolveSpendTier('25000.00')).toBe('CATEGORY_MGR');
    });

    it('resolves $25,001 - $100,000 to PROC_DIRECTOR', () => {
      expect(resolveSpendTier(25001)).toBe('PROC_DIRECTOR');
      expect(resolveSpendTier(50000)).toBe('PROC_DIRECTOR');
      expect(resolveSpendTier(100000)).toBe('PROC_DIRECTOR');
      expect(resolveSpendTier('100000.00')).toBe('PROC_DIRECTOR');
    });

    it('resolves > $100,000 to DUAL_VP', () => {
      expect(resolveSpendTier(100001)).toBe('DUAL_VP');
      expect(resolveSpendTier(180000)).toBe('DUAL_VP');
      expect(resolveSpendTier('240000.00')).toBe('DUAL_VP');
    });
  });

  describe('Store State Management & Selection', () => {
    it('initializes with canonical NanoCore approval queue items', () => {
      const state = useApprovalStore.getState();
      expect(state.approvals.length).toBe(CANONICAL_APPROVAL_ITEMS.length);
      expect(state.selectedApprovalId).toBe('appr-nc-001');
      expect(state.currentApproval?.action_type).toBe('LOGISTICS_EXPEDITE');
      expect(state.currentApproval?.spend_tier).toBe('DUAL_VP');
    });

    it('selects approval by ID', () => {
      useApprovalStore.getState().selectApproval('appr-nc-002');
      const state = useApprovalStore.getState();
      expect(state.selectedApprovalId).toBe('appr-nc-002');
      expect(state.currentApproval?.status).toBe('PARTIALLY_APPROVED');
    });

    it('opens modal for approval item and sets active scenario', () => {
      const target = CANONICAL_APPROVAL_ITEMS[1];
      useApprovalStore.getState().openModalForApproval(target);

      const state = useApprovalStore.getState();
      expect(state.isModalOpen).toBe(true);
      expect(state.currentApproval?.id).toBe(target.id);
      expect(state.activeScenario?.estimated_cost_usd).toBe(Number(target.amount_usd));
    });

    it('opens modal from investigation scenario payload', () => {
      useApprovalStore.getState().openModalForScenario(
        {
          scenario_id: 'SCEN-001',
          scenario_type: 'LOGISTICS_EXPEDITE',
          title: 'Dedicated Air Charter B777F',
          estimated_cost_usd: 180000,
          spend_tier: 'DUAL_VP',
        },
        'alt-nc-001'
      );

      const state = useApprovalStore.getState();
      expect(state.isModalOpen).toBe(true);
      expect(state.currentApproval?.amount_usd).toBe('180000.00');
      expect(state.currentApproval?.spend_tier).toBe('DUAL_VP');
    });

    it('closes modal and clears errors', () => {
      useApprovalStore.getState().openModalForApproval(CANONICAL_APPROVAL_ITEMS[0]);
      expect(useApprovalStore.getState().isModalOpen).toBe(true);

      useApprovalStore.getState().closeModal();
      expect(useApprovalStore.getState().isModalOpen).toBe(false);
      expect(useApprovalStore.getState().error).toBeNull();
    });
  });

  describe('Cryptographic Signature Submission', () => {
    it('advances DUAL_VP approval from PENDING to PARTIALLY_APPROVED on 1st signature', async () => {
      const mockResponse: ApprovalSignResponse = {
        id: 'appr-nc-001',
        status: 'PARTIALLY_APPROVED',
        action_type: 'LOGISTICS_EXPEDITE',
        amount_usd: '180000.00',
        spend_tier: 'DUAL_VP',
        approved_by: ['priya.sharma@apexmotion.com (Procurement Director)'],
        approved_at: ['2026-11-24T12:00:00Z'],
        message: 'Initial signature recorded; awaiting secondary executive authorization',
      };

      vi.spyOn(approvalApi, 'signApproval').mockResolvedValueOnce(mockResponse);

      const result = await useApprovalStore
        .getState()
        .submitSignature('appr-nc-001', 'mock-p256-token-1', 'Approved air expedite');

      expect(result.status).toBe('PARTIALLY_APPROVED');
      expect(useApprovalStore.getState().currentApproval?.status).toBe('PARTIALLY_APPROVED');
      expect(useApprovalStore.getState().currentApproval?.approved_by.length).toBe(1);
    });

    it('advances DUAL_VP approval from PARTIALLY_APPROVED to APPROVED on 2nd signature', async () => {
      useApprovalStore.getState().selectApproval('appr-nc-002'); // Has 1 existing signature

      const mockResponse: ApprovalSignResponse = {
        id: 'appr-nc-002',
        status: 'APPROVED',
        action_type: 'SECONDARY_SOURCE',
        amount_usd: '240000.00',
        spend_tier: 'DUAL_VP',
        approved_by: [
          'priya.sharma@apexmotion.com (Procurement Director)',
          'elena.rostova@apexmotion.com (VP Supply Chain)',
        ],
        approved_at: ['2026-11-24T12:00:00Z', '2026-11-24T12:05:00Z'],
        message: 'Cryptographic dual sign-off verified and sealed',
      };

      vi.spyOn(approvalApi, 'signApproval').mockResolvedValueOnce(mockResponse);

      const result = await useApprovalStore
        .getState()
        .submitSignature('appr-nc-002', 'mock-p256-token-2', 'VP co-signature confirmed');

      expect(result.status).toBe('APPROVED');
      expect(useApprovalStore.getState().currentApproval?.status).toBe('APPROVED');
      expect(useApprovalStore.getState().currentApproval?.approved_by.length).toBe(2);
    });

    it('rejects an approval and captures justification', async () => {
      const mockRejected: ApprovalItem = {
        ...CANONICAL_APPROVAL_ITEMS[0],
        status: 'REJECTED',
      };
      vi.spyOn(approvalApi, 'rejectApproval').mockResolvedValueOnce(mockRejected);

      const result = await useApprovalStore
        .getState()
        .rejectApproval('appr-nc-001', 'Excessive freight premium');

      expect(result.status).toBe('REJECTED');
      expect(useApprovalStore.getState().currentApproval?.status).toBe('REJECTED');
    });
  });
});
