/**
 * Risk Dashboard Page (P12-2)
 *
 * Assembles the operational enterprise dashboard:
 * - KPICards: Financial exposure, active disruptions, minimum days of cover.
 * - SeverityHeatMap: Cross-tier disruption intensity matrix.
 * - SupplierRiskTable: Multi-tier supplier inventory and risk ratings.
 * - AlertFeed: Reactive Kafka-driven WebSocket alert stream.
 * - Live bidirectional connection via useAlertWebSocket + useRiskStore.
 */

import React, { useEffect } from 'react';
import {
  Activity,
  RefreshCw,
  User,
} from 'lucide-react';
import { useAlertWebSocket } from '../hooks/useAlertWebSocket';
import { useRiskStore } from '../stores/useRiskStore';
import { AlertFeed } from '../components/AlertFeed/AlertFeed';
import { KPICards } from '../components/RiskDashboard/KPICards';
import { SeverityHeatMap } from '../components/RiskDashboard/SeverityHeatMap';
import { SupplierRiskTable } from '../components/RiskDashboard/SupplierRiskTable';

export interface RiskDashboardPageProps {
  onNavigateToInvestigation?: () => void;
}

export const RiskDashboardPage: React.FC<RiskDashboardPageProps> = ({
  onNavigateToInvestigation,
}) => {
  const {
    suppliers,
    alerts,
    liveAlerts,
    kpis,
    selectedSupplierId,
    selectedAlertId,
    filters,
    isLoading,
    isRefreshing,
    error,
    lastUpdated,
    fetchDashboardData,
    addLiveAlert,
    acknowledgeAlert,
    setSelectedSupplier,
    setSelectedAlert,
    setFilters,
    clearLiveAlerts,
  } = useRiskStore();

  // Wire Kafka-driven WebSocket real-time stream into Zustand store
  const { isConnected, isConnecting, error: wsError } = useAlertWebSocket({
    onAlert: addLiveAlert,
  });

  // Initial load
  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  return (
    <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans">
      {/* Top Application Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-[#0c111d]/90 backdrop-blur-md px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 shadow-md shadow-sky-500/20">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-white">
                ApexMotion
              </h1>
              <span className="rounded bg-sky-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-400 border border-sky-500/20">
                PROD v1.0
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Supplier Risk Intelligence & Cryptographic Spend Governance Platform
            </p>
          </div>
        </div>

        {/* Right Header Controls */}
        <div className="flex items-center gap-4">
          {/* Active User / Role Badge */}
          <div className="hidden sm:flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5 border border-slate-800 text-xs">
            <User className="h-3.5 w-3.5 text-sky-400" />
            <span className="text-slate-400">Role:</span>
            <span className="font-semibold text-slate-200">Supply Chain Analyst</span>
          </div>

          {/* Last Updated Timestamp */}
          {lastUpdated && (
            <span className="hidden md:inline font-mono text-xs text-slate-400">
              Updated {lastUpdated}
            </span>
          )}

          {/* Refresh Action */}
          <button
            type="button"
            onClick={() => fetchDashboardData()}
            disabled={isRefreshing || isLoading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors border border-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          {/* Investigation Dossier Navigation Action */}
          {onNavigateToInvestigation && (
            <button
              type="button"
              onClick={onNavigateToInvestigation}
              className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 px-3 py-1.5 text-xs font-bold text-white transition-colors shadow-sm"
            >
              <span>Investigation Dossier &rarr;</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Dashboard Layout */}
      <main className="flex-1 p-6 max-w-[1720px] w-full mx-auto space-y-6">
        {/* Error Alert Banner */}
        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-4 text-xs text-rose-300 flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => fetchDashboardData()}
              className="underline font-semibold ml-4"
            >
              Retry
            </button>
          </div>
        )}

        {/* Row 1: KPI Summary Cards & Triad Governance Banner */}
        <KPICards kpis={kpis} isLoading={isLoading} />

        {/* Row 2: 2-Column Responsive Workspace */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (8 of 12 cols): Severity Heatmap & Supplier Risk Table */}
          <div className="lg:col-span-8 space-y-6">
            {/* Severity Heat-Map Matrix */}
            <SeverityHeatMap
              suppliers={suppliers}
              activeRiskLevel={filters.riskLevel}
              activeTier={filters.tier}
              onSelectCell={(riskLevel, tier) => setFilters({ riskLevel, tier })}
            />

            {/* Supplier Risk Table */}
            <SupplierRiskTable
              suppliers={suppliers}
              selectedSupplierId={selectedSupplierId}
              onSelectSupplier={setSelectedSupplier}
              filters={filters}
              onFilterChange={setFilters}
              isLoading={isLoading}
            />
          </div>

          {/* Right Column (4 of 12 cols): Kafka Live Alert Feed */}
          <div className="lg:col-span-4 sticky top-20">
            <AlertFeed
              alerts={alerts}
              liveAlerts={liveAlerts}
              isConnected={isConnected}
              isConnecting={isConnecting}
              wsError={wsError}
              selectedAlertId={selectedAlertId}
              onSelectAlert={setSelectedAlert}
              onAcknowledgeAlert={acknowledgeAlert}
              onClearLiveAlerts={clearLiveAlerts}
            />
          </div>
        </div>
      </main>
    </div>
  );
};
