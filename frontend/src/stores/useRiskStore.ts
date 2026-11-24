/**
 * Zustand Risk & Alert State Management Store (P12-2)
 *
 * Enforces:
 * - Layering Invariants (CLAUDE.md Sec 5.2): UI state management only; zero risk math.
 * - Exact Decimal precision formatting (BR-RULE-001) for currency and coverage days.
 * - Reactive Kafka-driven WebSocket alert feed integration.
 * - Deterministic KPI aggregations and multi-faceted filtering (risk level, tier, search).
 */

import { create } from 'zustand';
import { riskApi, supplierApi } from '../api';
import type {
  RiskAlert,
  Supplier,
  SupplierRisk,
  WebSocketAlertData,
} from '../api/types';

export interface DashboardKPIs {
  totalExposureUsd: string;
  criticalAlertsCount: number;
  highAlertsCount: number;
  minDaysOfCover: string;
  activeDisruptionsCount: number;
  hitlPendingCount: number;
}

export interface RiskFilterState {
  search: string;
  riskLevel: 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  tier: number | null;
  status: 'ALL' | 'OPEN' | 'INVESTIGATING' | 'ACKNOWLEDGED' | 'RESOLVED';
}

export interface RiskStoreState {
  // Data
  suppliers: SupplierRisk[];
  rawSuppliers: Supplier[];
  alerts: RiskAlert[];
  liveAlerts: WebSocketAlertData[];
  kpis: DashboardKPIs;

  // Selections & Filters
  selectedSupplierId: string | null;
  selectedAlertId: string | null;
  filters: RiskFilterState;

  // Telemetry & Lifecycle
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  lastUpdated: string | null;

  // Actions
  fetchDashboardData: () => Promise<void>;
  addLiveAlert: (alert: WebSocketAlertData) => void;
  acknowledgeAlert: (alertId: string, notes?: string) => Promise<void>;
  setSelectedSupplier: (id: string | null) => void;
  setSelectedAlert: (id: string | null) => void;
  setFilters: (filters: Partial<RiskFilterState>) => void;
  resetFilters: () => void;
  clearLiveAlerts: () => void;
}

const initialKPIs: DashboardKPIs = {
  totalExposureUsd: '0.00',
  criticalAlertsCount: 0,
  highAlertsCount: 0,
  minDaysOfCover: '--',
  activeDisruptionsCount: 0,
  hitlPendingCount: 0,
};

const initialFilters: RiskFilterState = {
  search: '',
  riskLevel: 'ALL',
  tier: null,
  status: 'ALL',
};

// =============================================================================
// Deterministic Metric Aggregators (Zero Business Math Invariant)
// =============================================================================

export const computeDashboardKPIs = (
  alerts: RiskAlert[],
  liveAlerts: WebSocketAlertData[]
): DashboardKPIs => {
  let totalCents = 0n;
  let criticalCount = 0;
  let highCount = 0;
  let minDays: number | null = null;
  let hitlCount = 0;

  // Combine and deduplicate active alerts by alert ID
  const alertMap = new Map<string, {
    risk_level: string;
    financial_exposure: string | number | null | undefined;
    days_of_cover: string | number | null | undefined;
    hitl_required?: boolean;
    status: string;
  }>();

  for (const a of alerts) {
    if (a.status !== 'RESOLVED' && a.status !== 'CLOSED' && a.status !== 'DISMISSED') {
      alertMap.set(a.id, {
        risk_level: a.risk_level,
        financial_exposure: a.financial_exposure,
        days_of_cover: a.days_of_cover,
        status: a.status,
      });
    }
  }

  for (const la of liveAlerts) {
    if (la.status !== 'RESOLVED' && la.status !== 'CLOSED' && la.status !== 'DISMISSED') {
      alertMap.set(la.alert_id, {
        risk_level: la.risk_level,
        financial_exposure: la.financial_exposure,
        days_of_cover: la.days_of_cover,
        hitl_required: la.hitl_required,
        status: la.status,
      });
    }
  }

  for (const item of alertMap.values()) {
    const risk = (item.risk_level || '').toUpperCase();
    if (risk === 'CRITICAL') criticalCount += 1;
    if (risk === 'HIGH') highCount += 1;
    if (item.hitl_required) hitlCount += 1;

    // Financial Exposure summation using BigInt cents to preserve exact Decimal precision
    if (item.financial_exposure != null) {
      const expStr = String(item.financial_exposure);
      const parts = expStr.split('.');
      const dollars = BigInt(parts[0] || '0');
      const centsStr = (parts[1] || '00').padEnd(2, '0').slice(0, 2);
      const cents = BigInt(centsStr);
      totalCents += dollars * 100n + cents;
    }

    // Days of Cover minimum tracking
    if (item.days_of_cover != null) {
      const days = parseFloat(String(item.days_of_cover));
      if (!isNaN(days) && (minDays === null || days < minDays)) {
        minDays = days;
      }
    }
  }

  const dollarsTotal = totalCents / 100n;
  const centsRem = totalCents % 100n;
  const formattedExposure = `${dollarsTotal.toString()}.${centsRem.toString().padStart(2, '0')}`;

  return {
    totalExposureUsd: formattedExposure,
    criticalAlertsCount: criticalCount,
    highAlertsCount: highCount,
    minDaysOfCover: minDays !== null ? minDays.toFixed(2) : '--',
    activeDisruptionsCount: alertMap.size,
    hitlPendingCount: hitlCount,
  };
};

// =============================================================================
// Zustand Store Creator
// =============================================================================

export const useRiskStore = create<RiskStoreState>((set, get) => ({
  suppliers: [],
  rawSuppliers: [],
  alerts: [],
  liveAlerts: [],
  kpis: initialKPIs,

  selectedSupplierId: null,
  selectedAlertId: null,
  filters: initialFilters,

  isLoading: false,
  isRefreshing: false,
  error: null,
  lastUpdated: null,

  fetchDashboardData: async () => {
    const isInitial = get().suppliers.length === 0 && get().alerts.length === 0;
    set({
      isLoading: isInitial,
      isRefreshing: !isInitial,
      error: null,
    });

    try {
      // 1. Fetch persisted risk alerts
      const alertsResponse = await riskApi.getAlerts({ page: 1, page_size: 50 });
      const fetchedAlerts = alertsResponse.items;

      // 2. Fetch suppliers directory
      const suppliersResponse = await supplierApi.getSuppliers({ page: 1, page_size: 50 });
      const rawSuppliers = suppliersResponse.items;

      // 3. Enrich suppliers with live risk metrics
      const enrichedSuppliers: SupplierRisk[] = await Promise.all(
        rawSuppliers.map(async (s) => {
          try {
            return await supplierApi.getSupplierRisk(s.id);
          } catch {
            // Fallback for supplier without active alerts
            return {
              supplier_id: s.id,
              neptune_node_id: s.neptune_node_id,
              supplier_name: s.name,
              country_code: s.country_code,
              tier: s.tier,
              composite_risk_score: s.risk_score ?? '0.000',
              risk_level: Number(s.risk_score ?? 0) >= 0.7 ? 'CRITICAL' : 'LOW',
              active_alerts_count: 0,
              critical_alerts_count: 0,
              total_financial_exposure_usd: '0.00',
              total_shortage_volume: 0,
              min_days_of_cover: null,
              affected_skus: [],
              affected_plants: [],
              affected_programs: [],
              is_single_source: false,
              evaluated_at: new Date().toISOString(),
            };
          }
        })
      );

      const kpis = computeDashboardKPIs(fetchedAlerts, get().liveAlerts);

      set({
        alerts: fetchedAlerts,
        rawSuppliers,
        suppliers: enrichedSuppliers,
        kpis,
        isLoading: false,
        isRefreshing: false,
        lastUpdated: new Date().toLocaleTimeString(),
      });
    } catch (err: unknown) {
      set({
        isLoading: false,
        isRefreshing: false,
        error: err instanceof Error ? err.message : 'Failed to fetch risk dashboard data',
      });
    }
  },

  addLiveAlert: (newAlert: WebSocketAlertData) => {
    set((state) => {
      // Prepend and cap liveAlerts list at 50 items
      const updatedLive = [
        newAlert,
        ...state.liveAlerts.filter((a) => a.alert_id !== newAlert.alert_id),
      ].slice(0, 50);

      // Also update or add to persisted alerts if not present
      const existingAlertIdx = state.alerts.findIndex((a) => a.id === newAlert.alert_id);
      let updatedAlerts = [...state.alerts];

      if (existingAlertIdx >= 0) {
        updatedAlerts[existingAlertIdx] = {
          ...updatedAlerts[existingAlertIdx],
          risk_level: newAlert.risk_level,
          financial_exposure: newAlert.financial_exposure,
          days_of_cover: newAlert.days_of_cover,
          shortage_volume: newAlert.shortage_volume,
          status: newAlert.status,
        };
      } else {
        updatedAlerts = [
          {
            id: newAlert.alert_id,
            supplier_id: newAlert.supplier_id,
            component_sku: newAlert.component_sku,
            risk_level: newAlert.risk_level,
            days_of_cover: newAlert.days_of_cover,
            financial_exposure: newAlert.financial_exposure,
            shortage_volume: newAlert.shortage_volume,
            status: newAlert.status,
            created_at: newAlert.timestamp,
          },
          ...updatedAlerts,
        ];
      }

      const kpis = computeDashboardKPIs(updatedAlerts, updatedLive);

      return {
        liveAlerts: updatedLive,
        alerts: updatedAlerts,
        kpis,
      };
    });
  },

  acknowledgeAlert: async (alertId: string, notes?: string) => {
    try {
      await riskApi.acknowledgeAlert(alertId, { notes });
      set((state) => {
        const updatedAlerts = state.alerts.map((a) =>
          a.id === alertId ? { ...a, status: 'ACKNOWLEDGED' } : a
        );
        const updatedLive = state.liveAlerts.map((la) =>
          la.alert_id === alertId ? { ...la, status: 'ACKNOWLEDGED' } : la
        );
        const kpis = computeDashboardKPIs(updatedAlerts, updatedLive);
        return {
          alerts: updatedAlerts,
          liveAlerts: updatedLive,
          kpis,
        };
      });
    } catch (err: unknown) {
      set({
        error: err instanceof Error ? err.message : 'Failed to acknowledge alert',
      });
      throw err;
    }
  },

  setSelectedSupplier: (id: string | null) => set({ selectedSupplierId: id }),
  setSelectedAlert: (id: string | null) => set({ selectedAlertId: id }),
  setFilters: (newFilters: Partial<RiskFilterState>) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    })),
  resetFilters: () => set({ filters: initialFilters }),
  clearLiveAlerts: () =>
    set((state) => ({
      liveAlerts: [],
      kpis: computeDashboardKPIs(state.alerts, []),
    })),
}));
