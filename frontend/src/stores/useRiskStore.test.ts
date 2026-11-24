/**
 * Zustand Risk Store Unit Tests (P12-2)
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { riskApi, supplierApi } from '../api';
import type { RiskAlert, SupplierRisk, WebSocketAlertData } from '../api/types';
import { computeDashboardKPIs, useRiskStore } from './useRiskStore';

describe('computeDashboardKPIs Aggregator', () => {
  it('aggregates zero alerts into empty KPI defaults', () => {
    const kpis = computeDashboardKPIs([], []);
    expect(kpis.totalExposureUsd).toBe('0.00');
    expect(kpis.criticalAlertsCount).toBe(0);
    expect(kpis.highAlertsCount).toBe(0);
    expect(kpis.minDaysOfCover).toBe('--');
    expect(kpis.activeDisruptionsCount).toBe(0);
  });

  it('correctly aggregates canonical NanoCore golden scenario alert metrics', () => {
    const nanocoreAlert: RiskAlert = {
      id: 'alt-nc-1',
      supplier_id: 'sup-nanocore',
      component_sku: 'NC-2024',
      risk_level: 'CRITICAL',
      days_of_cover: '7.68',
      financial_exposure: '2448105.00',
      shortage_volume: 24420,
      status: 'OPEN',
      created_at: '2026-11-24T12:00:00Z',
    };

    const kpis = computeDashboardKPIs([nanocoreAlert], []);
    expect(kpis.totalExposureUsd).toBe('2448105.00');
    expect(kpis.criticalAlertsCount).toBe(1);
    expect(kpis.highAlertsCount).toBe(0);
    expect(kpis.minDaysOfCover).toBe('7.68');
    expect(kpis.activeDisruptionsCount).toBe(1);
  });

  it('combines and deduplicates live WebSocket alerts and persisted alerts', () => {
    const persistedAlert: RiskAlert = {
      id: 'alt-1',
      component_sku: 'MCU-01',
      risk_level: 'HIGH',
      days_of_cover: '12.00',
      financial_exposure: '50000.00',
      shortage_volume: 100,
      status: 'OPEN',
      created_at: '2026-11-24T10:00:00Z',
    };

    const liveAlert: WebSocketAlertData = {
      alert_id: 'alt-2',
      component_sku: 'NC-2024',
      risk_level: 'CRITICAL',
      days_of_cover: '7.68',
      financial_exposure: '2448105.00',
      shortage_volume: 24420,
      status: 'OPEN',
      hitl_required: true,
      timestamp: '2026-11-24T10:05:00Z',
    };

    const kpis = computeDashboardKPIs([persistedAlert], [liveAlert]);
    expect(kpis.totalExposureUsd).toBe('2498105.00');
    expect(kpis.criticalAlertsCount).toBe(1);
    expect(kpis.highAlertsCount).toBe(1);
    expect(kpis.minDaysOfCover).toBe('7.68');
    expect(kpis.activeDisruptionsCount).toBe(2);
    expect(kpis.hitlPendingCount).toBe(1);
  });

  it('ignores terminal alerts (RESOLVED, CLOSED, DISMISSED)', () => {
    const closedAlert: RiskAlert = {
      id: 'alt-closed',
      component_sku: 'CAP-99',
      risk_level: 'CRITICAL',
      days_of_cover: '2.00',
      financial_exposure: '100000.00',
      shortage_volume: 50,
      status: 'RESOLVED',
      created_at: '2026-11-24T08:00:00Z',
    };

    const kpis = computeDashboardKPIs([closedAlert], []);
    expect(kpis.activeDisruptionsCount).toBe(0);
    expect(kpis.totalExposureUsd).toBe('0.00');
  });
});

describe('useRiskStore Actions and State Transitions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useRiskStore.setState({
      suppliers: [],
      rawSuppliers: [],
      alerts: [],
      liveAlerts: [],
      selectedSupplierId: null,
      selectedAlertId: null,
      error: null,
    });
    useRiskStore.getState().resetFilters();
  });

  it('sets initial state correctly', () => {
    const state = useRiskStore.getState();
    expect(state.suppliers).toEqual([]);
    expect(state.alerts).toEqual([]);
    expect(state.liveAlerts).toEqual([]);
    expect(state.filters.riskLevel).toBe('ALL');
  });

  it('fetches dashboard data and enriches supplier risk metrics', async () => {
    const mockAlerts = {
      items: [
        {
          id: 'alt-1',
          component_sku: 'NC-2024',
          risk_level: 'CRITICAL',
          days_of_cover: '7.68',
          financial_exposure: '2448105.00',
          status: 'OPEN',
          created_at: '2026-11-24T12:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
      total_pages: 1,
    };

    const mockSuppliers = {
      items: [
        {
          id: 'sup-1',
          name: 'NanoCore Semiconductor',
          country_code: 'DE',
          tier: 1,
          risk_score: '0.920',
          neptune_node_id: 'SUP-NC-882',
          created_at: '2026-11-20T00:00:00Z',
          updated_at: '2026-11-24T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
      total_pages: 1,
    };

    const mockSupplierRisk: SupplierRisk = {
      supplier_id: 'sup-1',
      supplier_name: 'NanoCore Semiconductor',
      country_code: 'DE',
      tier: 1,
      composite_risk_score: '0.920',
      risk_level: 'CRITICAL',
      active_alerts_count: 1,
      critical_alerts_count: 1,
      total_financial_exposure_usd: '2448105.00',
      total_shortage_volume: 24420,
      min_days_of_cover: '7.68',
      affected_skus: ['NC-2024'],
      affected_plants: ['PLT-MUC-01'],
      affected_programs: ['PGM-APEX'],
      is_single_source: true,
      evaluated_at: '2026-11-24T12:00:00Z',
    };

    vi.spyOn(riskApi, 'getAlerts').mockResolvedValueOnce(mockAlerts);
    vi.spyOn(supplierApi, 'getSuppliers').mockResolvedValueOnce(mockSuppliers);
    vi.spyOn(supplierApi, 'getSupplierRisk').mockResolvedValueOnce(mockSupplierRisk);

    await useRiskStore.getState().fetchDashboardData();

    const state = useRiskStore.getState();
    expect(state.alerts).toHaveLength(1);
    expect(state.suppliers).toHaveLength(1);
    expect(state.suppliers[0].supplier_name).toBe('NanoCore Semiconductor');
    expect(state.kpis.totalExposureUsd).toBe('2448105.00');
    expect(state.kpis.criticalAlertsCount).toBe(1);
  });

  it('ingests live WebSocket alert and updates KPIs dynamically', () => {
    const liveAlert: WebSocketAlertData = {
      alert_id: 'alt-live-1',
      component_sku: 'NC-2024',
      risk_level: 'CRITICAL',
      days_of_cover: '7.68',
      financial_exposure: '2448105.00',
      shortage_volume: 24420,
      status: 'OPEN',
      hitl_required: true,
      hitl_tier: 'DUAL_VP',
      timestamp: '2026-11-24T12:00:00Z',
    };

    useRiskStore.getState().addLiveAlert(liveAlert);

    const state = useRiskStore.getState();
    expect(state.liveAlerts).toHaveLength(1);
    expect(state.liveAlerts[0].component_sku).toBe('NC-2024');
    expect(state.kpis.totalExposureUsd).toBe('2448105.00');
    expect(state.kpis.criticalAlertsCount).toBe(1);
  });

  it('acknowledges an alert and transitions state', async () => {
    const alert: RiskAlert = {
      id: 'alt-ack-1',
      component_sku: 'NC-2024',
      risk_level: 'CRITICAL',
      days_of_cover: '7.68',
      financial_exposure: '2448105.00',
      status: 'OPEN',
      created_at: '2026-11-24T12:00:00Z',
    };

    useRiskStore.setState({ alerts: [alert] });

    vi.spyOn(riskApi, 'acknowledgeAlert').mockResolvedValueOnce({
      id: 'alt-ack-1',
      status: 'ACKNOWLEDGED',
      acknowledged_by: 'usr-analyst',
      acknowledged_at: '2026-11-24T12:10:00Z',
      notes: 'Triage complete',
    });

    await useRiskStore.getState().acknowledgeAlert('alt-ack-1', 'Triage complete');

    const state = useRiskStore.getState();
    expect(state.alerts[0].status).toBe('ACKNOWLEDGED');
  });

  it('manages filter and selection mutations', () => {
    const store = useRiskStore.getState();
    store.setSelectedSupplier('sup-123');
    expect(useRiskStore.getState().selectedSupplierId).toBe('sup-123');

    store.setSelectedAlert('alt-999');
    expect(useRiskStore.getState().selectedAlertId).toBe('alt-999');

    store.setFilters({ riskLevel: 'CRITICAL', tier: 1 });
    expect(useRiskStore.getState().filters.riskLevel).toBe('CRITICAL');
    expect(useRiskStore.getState().filters.tier).toBe(1);

    store.resetFilters();
    expect(useRiskStore.getState().filters.riskLevel).toBe('ALL');
    expect(useRiskStore.getState().filters.tier).toBeNull();
  });
});
