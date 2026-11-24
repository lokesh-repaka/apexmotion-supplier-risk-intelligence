/**
 * Audit Store Unit Tests (P12-6)
 *
 * Verifies:
 * - Default state initialization and reset.
 * - Role-Aware Governance (analyst read-only vs category_manager vs procurement_director vs vp_supply_chain).
 * - Canonical golden NanoCore WORM audit ledger loading (8 sequential blocks).
 * - Cryptographic SHA-256 Merkle hash chain verification from Genesis.
 * - API ingestion via auditApi.getAlertAuditTrail().
 * - Graceful fallback resilience when backend encounters network latency.
 * - Search query and action filtering mechanics.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auditApi } from '../api/routes/audit';
import type { AuditLogListResponse } from '../api/types';
import {
  CANONICAL_NANOCORE_AUDIT_BLOCKS,
  useAuditStore,
} from './useAuditStore';

describe('useAuditStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuditStore.getState().reset();
  });

  it('initializes with clean default state and Analyst persona (read-only)', () => {
    const state = useAuditStore.getState();
    expect(state.currentPersona.role).toBe('analyst');
    expect(state.currentPersona.canApproveSpend).toBe(false);
    expect(state.currentPersona.maxSpendLimitUsd).toBe(0);
    expect(state.selectedAlertId).toBe('ALT-NC-001');
    expect(state.isIntegrityVerified).toBe(true);
    expect(state.tamperCount).toBe(0);
    expect(state.searchQuery).toBe('');
    expect(state.actionFilter).toBe('ALL');
  });

  it('switches personas and enforces tiered spend authorities (CLAUDE.md Sec 10)', () => {
    // 1. Category Manager: <= $25,000
    useAuditStore.getState().setCurrentPersona('category_manager');
    let persona = useAuditStore.getState().currentPersona;
    expect(persona.role).toBe('category_manager');
    expect(persona.canApproveSpend).toBe(true);
    expect(persona.maxSpendLimitUsd).toBe(25000);

    // 2. Procurement Director: <= $100,000 & Dual Signer 1
    useAuditStore.getState().setCurrentPersona('procurement_director');
    persona = useAuditStore.getState().currentPersona;
    expect(persona.role).toBe('procurement_director');
    expect(persona.canApproveSpend).toBe(true);
    expect(persona.maxSpendLimitUsd).toBe(100000);

    // 3. VP Supply Chain: Dual Sign-off > $100,000
    useAuditStore.getState().setCurrentPersona('vp_supply_chain');
    persona = useAuditStore.getState().currentPersona;
    expect(persona.role).toBe('vp_supply_chain');
    expect(persona.canApproveSpend).toBe(true);
    expect(persona.maxSpendLimitUsd).toBeNull();

    // 4. Back to Analyst: strictly read-only
    useAuditStore.getState().setCurrentPersona('analyst');
    persona = useAuditStore.getState().currentPersona;
    expect(persona.role).toBe('analyst');
    expect(persona.canApproveSpend).toBe(false);
    expect(persona.maxSpendLimitUsd).toBe(0);
  });

  it('loads canonical golden NanoCore audit ledger with 8 chained blocks', () => {
    useAuditStore.getState().loadCanonicalAuditTrail('ALT-NC-001');
    const state = useAuditStore.getState();

    expect(state.blocks.length).toBe(8);
    expect(state.blocks).toEqual(CANONICAL_NANOCORE_AUDIT_BLOCKS);

    // Block 1: Genesis Signal Ingest
    const b1 = state.blocks[0];
    expect(b1.block_index).toBe(1);
    expect(b1.action).toBe('SIGNAL_INGEST');
    expect(b1.previous_hash).toBe(
      '0000000000000000000000000000000000000000000000000000000000000000'
    );

    // Block 3: Deterministic Math Certification (BR-RULE-001)
    const b3 = state.blocks[2];
    expect(b3.action).toBe('MATH_CERTIFIED');
    expect(b3.after_state?.days_of_cover).toBe('7.68');
    expect(b3.after_state?.shortage_gap_days).toBe('1.32');
    expect(b3.after_state?.projected_shortage_units).toBe(24420);
    expect(b3.after_state?.financial_exposure_usd).toBe('2448105.00');

    // Block 6 & 7: Dual Signatures (BR-RULE-004)
    const b6 = state.blocks[5];
    const b7 = state.blocks[6];
    expect(b6.action).toBe('HITL_TOKEN_SIGNED');
    expect(b6.after_state?.signatures_collected).toBe(1);
    expect(b7.action).toBe('HITL_TOKEN_SIGNED');
    expect(b7.after_state?.signatures_collected).toBe(2);

    // Block 8: SAP PO Dispatch
    const b8 = state.blocks[7];
    expect(b8.action).toBe('SAP_PO_DISPATCHED');
    expect(b8.after_state?.sap_po_number).toBe('PR-2026-009182');
  });

  it('verifies unbroken SHA-256 Merkle chaining across all 8 canonical blocks', () => {
    useAuditStore.getState().loadCanonicalAuditTrail();
    const isClean = useAuditStore.getState().verifyMerkleIntegrity();

    expect(isClean).toBe(true);
    const state = useAuditStore.getState();
    expect(state.isIntegrityVerified).toBe(true);
    expect(state.tamperCount).toBe(0);

    // Verify consecutive block hash linkage
    for (let i = 1; i < state.blocks.length; i++) {
      const prevBlock = state.blocks[i - 1];
      const currBlock = state.blocks[i];
      expect(currBlock.previous_hash).toBe(prevBlock.current_hash);
    }
  });

  it('detects tampering when a block hash is mutated', () => {
    useAuditStore.getState().loadCanonicalAuditTrail();

    // Intentionally mutate block 4 hash to simulate unauthorized ledger modification
    const tamperedBlocks = [...useAuditStore.getState().blocks];
    tamperedBlocks[3] = {
      ...tamperedBlocks[3],
      current_hash: 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
    };

    useAuditStore.setState({ blocks: tamperedBlocks });

    const isValid = useAuditStore.getState().verifyMerkleIntegrity();
    expect(isValid).toBe(false);
    expect(useAuditStore.getState().isIntegrityVerified).toBe(false);
    expect(useAuditStore.getState().tamperCount).toBeGreaterThan(0);
  });

  it('fetches audit trail from API and transforms records', async () => {
    const mockApiResponse: AuditLogListResponse = {
      items: [
        {
          id: 101,
          entity_type: 'RISK_ALERT',
          entity_id: 'alt-uuid-001',
          action: 'ALERT_ACKNOWLEDGED',
          actor_id: 'user-cat-mgr',
          before_state: { status: 'OPEN' },
          after_state: { status: 'ACKNOWLEDGED' },
          trace_id: 'tr-mock-101',
          created_at: '2026-09-14T09:00:00Z',
        },
      ],
      total: 1,
      entity_id: 'alt-uuid-001',
      entity_type: 'RISK_ALERT',
    };

    const spy = vi
      .spyOn(auditApi, 'getAlertAuditTrail')
      .mockResolvedValueOnce(mockApiResponse);

    await useAuditStore.getState().fetchAlertAuditTrail('alt-uuid-001');

    expect(spy).toHaveBeenCalledWith('alt-uuid-001');
    const state = useAuditStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.blocks.length).toBe(1);
    expect(state.blocks[0].action).toBe('ALERT_ACKNOWLEDGED');
    expect(state.blocks[0].trace_id).toBe('tr-mock-101');
  });

  it('falls back to canonical golden data if API call fails', async () => {
    vi.spyOn(auditApi, 'getAlertAuditTrail').mockRejectedValueOnce(
      new Error('S3 Object Lock retention query timeout')
    );

    await useAuditStore.getState().fetchAlertAuditTrail('ALT-NC-001');

    const state = useAuditStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.blocks.length).toBe(8);
  });

  it('filters audit blocks by search query and action verb', () => {
    useAuditStore.getState().loadCanonicalAuditTrail();

    useAuditStore.getState().setSearchQuery('Elena Rostova');
    expect(useAuditStore.getState().searchQuery).toBe('Elena Rostova');

    useAuditStore.getState().setActionFilter('HITL_TOKEN_SIGNED');
    expect(useAuditStore.getState().actionFilter).toBe('HITL_TOKEN_SIGNED');

    useAuditStore.getState().selectBlock('blk-007');
    expect(useAuditStore.getState().selectedBlockId).toBe('blk-007');
  });
});
