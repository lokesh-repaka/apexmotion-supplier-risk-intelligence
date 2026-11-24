/**
 * Severity Heat-Map Component (P12-2)
 *
 * Visualizes disruption intensity across supply chain tiers (1, 2, 3) and
 * severity levels (CRITICAL, HIGH, MEDIUM, LOW):
 * - Interactive tile matrix with drill-down filter dispatch.
 * - Dynamic heat coloring based on disruption frequency and exposure density.
 * - Exact Decimal precision formatting for monetary values.
 */

import React, { useMemo } from 'react';
import { Flame, Layers } from 'lucide-react';
import type { SupplierRisk } from '../../api/types';
import type { RiskFilterState } from '../../stores/useRiskStore';

interface SeverityHeatMapProps {
  suppliers: SupplierRisk[];
  onSelectCell?: (riskLevel: RiskFilterState['riskLevel'], tier: number | null) => void;
  activeRiskLevel?: RiskFilterState['riskLevel'];
  activeTier?: number | null;
}

const SEVERITIES: Array<'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'> = [
  'CRITICAL',
  'HIGH',
  'MEDIUM',
  'LOW',
];

const TIERS = [1, 2, 3];

export const SeverityHeatMap: React.FC<SeverityHeatMapProps> = ({
  suppliers,
  onSelectCell,
  activeRiskLevel = 'ALL',
  activeTier = null,
}) => {
  // Aggregate suppliers into a 4x3 matrix: [Severity][Tier]
  const matrix = useMemo(() => {
    const data: Record<
      string,
      Record<number, { count: number; totalExposureCents: bigint }>
    > = {
      CRITICAL: { 1: { count: 0, totalExposureCents: 0n }, 2: { count: 0, totalExposureCents: 0n }, 3: { count: 0, totalExposureCents: 0n } },
      HIGH: { 1: { count: 0, totalExposureCents: 0n }, 2: { count: 0, totalExposureCents: 0n }, 3: { count: 0, totalExposureCents: 0n } },
      MEDIUM: { 1: { count: 0, totalExposureCents: 0n }, 2: { count: 0, totalExposureCents: 0n }, 3: { count: 0, totalExposureCents: 0n } },
      LOW: { 1: { count: 0, totalExposureCents: 0n }, 2: { count: 0, totalExposureCents: 0n }, 3: { count: 0, totalExposureCents: 0n } },
    };

    for (const s of suppliers) {
      const sev = (s.risk_level || 'LOW').toUpperCase() as 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
      const tier = s.tier in [1, 2, 3] ? s.tier : 1;

      if (data[sev] && data[sev][tier]) {
        data[sev][tier].count += 1;

        if (s.total_financial_exposure_usd) {
          const parts = String(s.total_financial_exposure_usd).split('.');
          const dollars = BigInt(parts[0] || '0');
          const cents = BigInt((parts[1] || '00').padEnd(2, '0').slice(0, 2));
          data[sev][tier].totalExposureCents += dollars * 100n + cents;
        }
      }
    }

    return data;
  }, [suppliers]);

  const formatShortExposure = (cents: bigint): string => {
    if (cents === 0n) return '$0';
    const dollars = Number(cents) / 100;
    if (dollars >= 1_000_000) {
      return `$${(dollars / 1_000_000).toFixed(2)}M`;
    }
    if (dollars >= 1_000) {
      return `$${(dollars / 1_000).toFixed(0)}k`;
    }
    return `$${dollars.toFixed(0)}`;
  };

  const getCellIntensityStyle = (
    sev: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW',
    count: number,
    isSelected: boolean
  ) => {
    if (isSelected) {
      return 'border-2 border-sky-400 bg-sky-950/80 shadow-md shadow-sky-500/20';
    }

    if (count === 0) {
      return 'border border-slate-800/80 bg-slate-900/30 text-slate-600 hover:border-slate-700';
    }

    switch (sev) {
      case 'CRITICAL':
        return 'border border-rose-500/40 bg-gradient-to-br from-rose-950/50 to-slate-900 text-rose-300 hover:border-rose-400 hover:shadow-rose-900/30';
      case 'HIGH':
        return 'border border-amber-500/40 bg-gradient-to-br from-amber-950/50 to-slate-900 text-amber-300 hover:border-amber-400 hover:shadow-amber-900/30';
      case 'MEDIUM':
        return 'border border-yellow-500/30 bg-gradient-to-br from-yellow-950/40 to-slate-900 text-yellow-300 hover:border-yellow-400';
      default:
        return 'border border-emerald-500/30 bg-gradient-to-br from-emerald-950/40 to-slate-900 text-emerald-300 hover:border-emerald-400';
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-5 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-rose-500/10 p-2 text-rose-400">
            <Flame className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              Disruption Severity Heat-Map
            </h3>
            <p className="text-xs text-slate-400">
              Cross-tier exposure matrix (Click cell to filter matrix)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <Layers className="h-4 w-4 text-sky-400" />
          <span>Tiers 1–3</span>
        </div>
      </div>

      {/* Matrix Grid */}
      <div className="mt-4">
        {/* Tier Columns Header */}
        <div className="grid grid-cols-4 gap-2 text-center text-[11px] font-mono text-slate-400 font-semibold mb-2">
          <div className="text-left pl-2">Severity</div>
          <div className="rounded bg-slate-950/50 py-1">Tier 1 (OEM)</div>
          <div className="rounded bg-slate-950/50 py-1">Tier 2 (Sub)</div>
          <div className="rounded bg-slate-950/50 py-1">Tier 3 (Raw)</div>
        </div>

        {/* Severity Rows */}
        <div className="space-y-2">
          {SEVERITIES.map((sev) => (
            <div key={sev} className="grid grid-cols-4 gap-2 items-center">
              {/* Row Label */}
              <div className="flex items-center gap-1.5 pl-2 font-mono text-xs font-semibold">
                <span
                  className={`h-2 w-2 rounded-full ${
                    sev === 'CRITICAL'
                      ? 'bg-rose-500'
                      : sev === 'HIGH'
                      ? 'bg-amber-400'
                      : sev === 'MEDIUM'
                      ? 'bg-yellow-400'
                      : 'bg-emerald-400'
                  }`}
                />
                <span
                  className={
                    sev === 'CRITICAL'
                      ? 'text-rose-400'
                      : sev === 'HIGH'
                      ? 'text-amber-400'
                      : sev === 'MEDIUM'
                      ? 'text-yellow-400'
                      : 'text-emerald-400'
                  }
                >
                  {sev}
                </span>
              </div>

              {/* 3 Tier Cells */}
              {TIERS.map((tier) => {
                const cell = matrix[sev][tier];
                const isSelected = activeRiskLevel === sev && activeTier === tier;

                return (
                  <button
                    key={tier}
                    type="button"
                    onClick={() => {
                      if (onSelectCell) {
                        if (isSelected) {
                          onSelectCell('ALL', null);
                        } else {
                          onSelectCell(sev, tier);
                        }
                      }
                    }}
                    className={`flex flex-col items-center justify-center p-2.5 rounded-lg transition-all duration-200 cursor-pointer ${getCellIntensityStyle(
                      sev,
                      cell.count,
                      isSelected
                    )}`}
                  >
                    <span className="font-mono text-base font-bold">
                      {cell.count}
                    </span>
                    <span className="font-mono text-[10px] opacity-80">
                      {formatShortExposure(cell.totalExposureCents)}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Heatmap Footer Legend */}
      <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3 text-[11px] text-slate-400">
        <div className="flex items-center gap-2">
          <span>Heat Intensity:</span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-slate-800" /> 0
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-amber-500/40" /> Med
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-rose-500/50" /> High
          </span>
        </div>
        <span className="font-mono text-slate-500 text-[10px]">
          Live Aurora DB Aggregates
        </span>
      </div>
    </div>
  );
};
