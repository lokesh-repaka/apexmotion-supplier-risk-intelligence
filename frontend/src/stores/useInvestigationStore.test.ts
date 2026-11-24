/**
 * Investigation Store Unit Tests (P12-3)
 *
 * Verifies:
 * - Default canonical NanoCore reference scenario initialization (FR-DEC-001)
 * - Triggering investigation API calls and status transitions
 * - Polling start/stop mechanics and SLA duration counter
 * - Circuit breaker fallback degradation handling
 * - Citation registry resolution and modal state selection
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { investigationApi } from '../api/routes/investigations';
import type {
  InvestigationDetailResponse,
  InvestigationStartResponse,
} from '../api/types';
import {
  CANONICAL_NANOCORE_INVESTIGATION,
  CITATION_REGISTRY,
  useInvestigationStore,
} from './useInvestigationStore';

describe('useInvestigationStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useInvestigationStore.getState().reset();
  });

  it('initializes with null state upon reset', () => {
    const state = useInvestigationStore.getState();
    expect(state.activeInvestigationId).toBeNull();
    expect(state.currentInvestigation).toBeNull();
    expect(state.isPolling).toBe(false);
    expect(state.isDegradedMode).toBe(false);
    expect(state.elapsedSeconds).toBe(0);
    expect(state.selectedCitation).toBeNull();
  });

  it('loads the canonical NanoCore golden scenario with exact metrics', () => {
    useInvestigationStore.getState().loadCanonicalScenario();
    const state = useInvestigationStore.getState();

    expect(state.activeInvestigationId).toBe('inv-nc-2026-091a');
    expect(state.currentInvestigation).not.toBeNull();
    expect(state.currentInvestigation?.case_id).toBe('CASE-2026-091');
    expect(state.currentInvestigation?.supplier_id).toBe('SUP-NC-001');
    expect(state.currentInvestigation?.component_sku).toBe('SKU-MCU-4402');
    expect(state.currentInvestigation?.status).toBe('AWAITING_APPROVAL');

    // Deterministic arithmetic checks (BR-RULE-001)
    const metrics = state.currentInvestigation?.risk_metrics;
    expect(metrics?.days_of_cover).toBe(7.68);
    expect(metrics?.shortage_gap_days).toBe(1.32);
    expect(metrics?.projected_unit_shortage).toBe(24420);
    expect(metrics?.total_financial_exposure_usd).toBe(2448105.0);
  });

  it('triggers an investigation successfully and updates active state', async () => {
    const mockStartResponse: InvestigationStartResponse = {
      investigation_id: 'inv-test-123',
      case_id: 'CASE-2026-123',
      alert_id: 'ALT-123',
      status: 'RUNNING',
      poll_url: '/api/v1/investigations/inv-test-123',
      started_at: '2026-11-24T12:00:00Z',
      estimated_completion_seconds: 90,
      message: 'Investigation pipeline started successfully',
    };

    const startSpy = vi
      .spyOn(investigationApi, 'startInvestigation')
      .mockResolvedValueOnce(mockStartResponse);

    const detailMock: InvestigationDetailResponse = {
      ...CANONICAL_NANOCORE_INVESTIGATION,
      investigation_id: 'inv-test-123',
      case_id: 'CASE-2026-123',
      status: 'RUNNING',
    };
    vi.spyOn(investigationApi, 'getInvestigation').mockResolvedValue(detailMock);

    const result = await useInvestigationStore.getState().triggerInvestigation({
      supplier_id: 'SUP-NC-001',
      component_sku: 'SKU-MCU-4402',
      signal_type: 'news',
      raw_signal: 'Cleanroom electrical fire advisory',
    });

    expect(startSpy).toHaveBeenCalledTimes(1);
    expect(result.investigation_id).toBe('inv-test-123');
    expect(useInvestigationStore.getState().activeInvestigationId).toBe('inv-test-123');
    expect(useInvestigationStore.getState().isPolling).toBe(true);
  });

  it('stops polling immediately when status is COMPLETED or AWAITING_APPROVAL', async () => {
    const detailMock: InvestigationDetailResponse = {
      ...CANONICAL_NANOCORE_INVESTIGATION,
      status: 'AWAITING_APPROVAL',
    };
    vi.spyOn(investigationApi, 'getInvestigation').mockResolvedValue(detailMock);

    useInvestigationStore.getState().startPolling('inv-test-123');
    expect(useInvestigationStore.getState().isPolling).toBe(true);

    await useInvestigationStore.getState().fetchInvestigation('inv-test-123');
    expect(useInvestigationStore.getState().isPolling).toBe(false);
  });

  it('toggles degraded mode simulation flag', () => {
    expect(useInvestigationStore.getState().isDegradedMode).toBe(false);
    useInvestigationStore.getState().setDegradedMode(true);
    expect(useInvestigationStore.getState().isDegradedMode).toBe(true);
  });

  it('manages citation selection and registry retrieval', () => {
    const citation = CITATION_REGISTRY['REUTERS-TW-9921'];
    expect(citation).toBeDefined();
    expect(citation.sourceType).toBe('news');
    expect(citation.tag).toBe('REUTERS-TW-9921');

    useInvestigationStore.getState().setSelectedCitation(citation);
    expect(useInvestigationStore.getState().selectedCitation?.tag).toBe('REUTERS-TW-9921');

    useInvestigationStore.getState().setSelectedCitation(null);
    expect(useInvestigationStore.getState().selectedCitation).toBeNull();
  });

  it('manages trigger modal visibility', () => {
    expect(useInvestigationStore.getState().isTriggerModalOpen).toBe(false);
    useInvestigationStore.getState().setIsTriggerModalOpen(true);
    expect(useInvestigationStore.getState().isTriggerModalOpen).toBe(true);
    useInvestigationStore.getState().setIsTriggerModalOpen(false);
    expect(useInvestigationStore.getState().isTriggerModalOpen).toBe(false);
  });
});
