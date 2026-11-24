/**
 * KPI Summary Cards Component (P12-2)
 *
 * Displays executive summary telemetry:
 * - Total Financial Exposure (exact Decimal precision)
 * - Critical & High Disruption Alerts count
 * - Minimum Days of Cover remaining
 * - Pending HITL Spend Approvals count
 * - The Triad of Responsibility governance banner (BR-RULE-001)
 */

import React from 'react';
import {
  AlertTriangle,
  Clock,
  DollarSign,
  Lock,
} from 'lucide-react';
import type { DashboardKPIs } from '../../stores/useRiskStore';

interface KPICardsProps {
  kpis: DashboardKPIs;
  isLoading?: boolean;
}

export const KPICards: React.FC<KPICardsProps> = ({ kpis, isLoading = false }) => {
  // Format monetary value with comma grouping
  const formatCurrency = (val: string): string => {
    const parts = val.split('.');
    const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const decimalPart = parts[1] || '00';
    return `$${integerPart}.${decimalPart}`;
  };

  return (
    <div className="space-y-4">
      {/* Triad of Responsibility Banner (BR-RULE-001) */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-500/20 bg-gradient-to-r from-sky-950/40 via-slate-900/60 to-indigo-950/40 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-semibold tracking-wider text-sky-400 uppercase">
            Triad of Separation Guardrail (BR-RULE-001)
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-slate-300 font-mono text-[11px]">
          <span className="flex items-center gap-1.5">
            <span className="text-slate-500">1.</span>
            <span className="text-sky-300 font-medium">AI Evidence Synthesis</span>
            <span className="text-slate-500">(Zero Math)</span>
          </span>
          <span className="text-slate-600">|</span>
          <span className="flex items-center gap-1.5">
            <span className="text-slate-500">2.</span>
            <span className="text-emerald-300 font-medium">Deterministic Python Engine</span>
            <span className="text-slate-500">(100% Arithmetic)</span>
          </span>
          <span className="text-slate-600">|</span>
          <span className="flex items-center gap-1.5">
            <span className="text-slate-500">3.</span>
            <span className="text-amber-300 font-medium">KMS ECDSA HITL Authority</span>
            <span className="text-slate-500">(Cryptographic Gate)</span>
          </span>
        </div>
      </div>

      {/* 4-Column KPI Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Total Financial Exposure */}
        <div className="relative overflow-hidden rounded-xl border border-rose-500/30 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-rose-500/50">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium tracking-wider text-rose-400 uppercase">
              Total Financial Exposure
            </span>
            <div className="rounded-lg bg-rose-500/10 p-2 text-rose-400">
              <DollarSign className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3">
            <div className="font-mono text-2xl font-bold tracking-tight text-white">
              {isLoading ? (
                <div className="h-8 w-32 animate-pulse rounded bg-slate-800" />
              ) : (
                formatCurrency(kpis.totalExposureUsd)
              )}
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Aggregated shortage and plant line halt risk
            </p>
          </div>
          <div className="absolute -bottom-6 -right-6 h-20 w-20 rounded-full bg-rose-500/5 blur-xl pointer-events-none" />
        </div>

        {/* Active Disruption Alerts */}
        <div className="relative overflow-hidden rounded-xl border border-amber-500/30 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-amber-500/50">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium tracking-wider text-amber-400 uppercase">
              Active Disruptions
            </span>
            <div className="rounded-lg bg-amber-500/10 p-2 text-amber-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-2xl font-bold tracking-tight text-white">
                {isLoading ? (
                  <div className="h-8 w-16 animate-pulse rounded bg-slate-800" />
                ) : (
                  kpis.activeDisruptionsCount
                )}
              </span>
              <span className="text-xs text-slate-400">alerts</span>
            </div>
            <div className="mt-2 flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 font-mono text-rose-400 font-semibold">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                {kpis.criticalAlertsCount} Critical
              </span>
              <span className="flex items-center gap-1 font-mono text-amber-400">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                {kpis.highAlertsCount} High
              </span>
            </div>
          </div>
          <div className="absolute -bottom-6 -right-6 h-20 w-20 rounded-full bg-amber-500/5 blur-xl pointer-events-none" />
        </div>

        {/* Lowest Days of Cover */}
        <div className="relative overflow-hidden rounded-xl border border-sky-500/30 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-sky-500/50">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium tracking-wider text-sky-400 uppercase">
              Min Days of Cover
            </span>
            <div className="rounded-lg bg-sky-500/10 p-2 text-sky-400">
              <Clock className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-2xl font-bold tracking-tight text-white">
                {isLoading ? (
                  <div className="h-8 w-20 animate-pulse rounded bg-slate-800" />
                ) : (
                  `${kpis.minDaysOfCover} d`
                )}
              </span>
              {kpis.minDaysOfCover === '7.68' && (
                <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300">
                  NanoCore Gap
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Stock burn buffer before line halt occurs
            </p>
          </div>
          <div className="absolute -bottom-6 -right-6 h-20 w-20 rounded-full bg-sky-500/5 blur-xl pointer-events-none" />
        </div>

        {/* HITL Spend Approvals Required */}
        <div className="relative overflow-hidden rounded-xl border border-indigo-500/30 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-indigo-500/50">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium tracking-wider text-indigo-400 uppercase">
              Pending Spend Gates
            </span>
            <div className="rounded-lg bg-indigo-500/10 p-2 text-indigo-400">
              <Lock className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-2xl font-bold tracking-tight text-white">
                {isLoading ? (
                  <div className="h-8 w-16 animate-pulse rounded bg-slate-800" />
                ) : (
                  kpis.hitlPendingCount
                )}
              </span>
              <span className="text-xs text-slate-400">authorizations</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Awaiting KMS ECDSA sign-off (Dual-VP / Director)
            </p>
          </div>
          <div className="absolute -bottom-6 -right-6 h-20 w-20 rounded-full bg-indigo-500/5 blur-xl pointer-events-none" />
        </div>
      </div>
    </div>
  );
};
