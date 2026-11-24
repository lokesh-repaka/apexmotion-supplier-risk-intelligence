/**
 * Mitigation Scenarios List Component (P12-3)
 *
 * Displays ranked mitigation scenarios from the Multi-Agent Recommendation Agent:
 * - Option 1: Logistics Acceleration (Air Charter)
 * - Option 2: Secondary Sourcing (MicroChip Global)
 * - Option 3: Production Line Rebalancing
 *
 * Previews required spend approval tiers and bridges directly into HITL Approval Modal (P12-4).
 */

import React from 'react';
import { ArrowRight, Sparkles, TrendingUp, Zap } from 'lucide-react';

interface ScenarioItem {
  scenario_id: string;
  scenario_type?: string;
  title?: string;
  description?: string;
  estimated_cost_usd: number;
  lead_time_days: number;
  net_benefit_usd?: number;
  spend_tier?: string;
  requires_hitl?: boolean;
}

interface MitigationScenariosListProps {
  recommendations: Array<Record<string, unknown>> | null;
  recommendedActionId?: string | null;
  onProceedToApproval?: (scenario: ScenarioItem) => void;
}

export const MitigationScenariosList: React.FC<MitigationScenariosListProps> = ({
  recommendations,
  recommendedActionId,
  onProceedToApproval,
}) => {
  const scenarios: ScenarioItem[] = (recommendations || []).map((r, i) => ({
    scenario_id: String(r.scenario_id || `SCEN-00${i + 1}`),
    scenario_type: String(r.scenario_type || 'LOGISTICS_EXPEDITE'),
    title: String(r.title || `Mitigation Option ${i + 1}`),
    description: String(r.description || ''),
    estimated_cost_usd: Number(r.estimated_cost_usd || 0),
    lead_time_days: Number(r.lead_time_days || 0),
    net_benefit_usd: Number(r.net_benefit_usd || 0),
    spend_tier: String(r.spend_tier || 'PROC_DIRECTOR'),
    requires_hitl: Boolean(r.requires_hitl ?? true),
  }));

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case 'CATEGORY_MGR':
        return {
          label: 'Category Manager (Spend <= $25k)',
          color: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
        };
      case 'PROC_DIRECTOR':
        return {
          label: 'Procurement Director (Spend $25k–$100k)',
          color: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
        };
      case 'DUAL_VP':
        return {
          label: 'Dual Sign-Off (VP + Director > $100k)',
          color: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
        };
      default:
        return {
          label: `${tier} Approval Required`,
          color: 'bg-slate-800 text-slate-300 border-slate-700',
        };
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-5 shadow-lg space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <TrendingUp className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Ranked Mitigation Scenarios &middot; Recommendation Agent
            </h3>
            <p className="text-[11px] text-slate-400">
              Pre-Compiled Decision Models with Cryptographic HITL Spend Authority
            </p>
          </div>
        </div>

        <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-2.5 py-1 text-[11px] font-semibold text-indigo-400 border border-indigo-500/20">
          <Sparkles className="h-3 w-3" />
          <span>3 Pre-Evaluated Options</span>
        </span>
      </div>

      {/* Scenarios List */}
      <div className="space-y-3">
        {scenarios.map((scen, idx) => {
          const isTopRecommended =
            scen.scenario_id === recommendedActionId || (!recommendedActionId && idx === 0);
          const tier = getTierBadge(scen.spend_tier || 'PROC_DIRECTOR');

          return (
            <div
              key={scen.scenario_id}
              className={`rounded-xl border p-4 transition-all ${
                isTopRecommended
                  ? 'border-sky-500/60 bg-sky-950/20 shadow-md shadow-sky-500/10 ring-1 ring-sky-500/30'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  {isTopRecommended && (
                    <span className="inline-flex items-center gap-1 rounded bg-sky-500 px-1.5 py-0.5 text-[10px] font-bold text-slate-950">
                      <Zap className="h-2.5 w-2.5 fill-current" /> TOP RECOMMENDED
                    </span>
                  )}
                  <span className="font-mono text-xs font-bold text-slate-400">
                    {scen.scenario_id}
                  </span>
                  <h4 className="text-xs sm:text-sm font-bold text-white">{scen.title}</h4>
                </div>

                {/* HITL Spend Tier Badge */}
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${tier.color}`}
                >
                  {tier.label}
                </span>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed mb-3">{scen.description}</p>

              {/* Metrics Row */}
              <div className="grid grid-cols-3 gap-2 py-2 border-y border-slate-800/80 text-xs font-mono">
                <div>
                  <span className="text-[10px] text-slate-500 uppercase block font-sans">
                    Estimated Cost:
                  </span>
                  <span className="font-bold text-white">
                    ${scen.estimated_cost_usd.toLocaleString('en-US')}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 uppercase block font-sans">
                    Lead Time:
                  </span>
                  <span className="font-bold text-amber-400">{scen.lead_time_days} Days</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 uppercase block font-sans">
                    Net Savings:
                  </span>
                  <span className="font-bold text-emerald-400">
                    ${(scen.net_benefit_usd || 0).toLocaleString('en-US')}
                  </span>
                </div>
              </div>

              {/* Action Button */}
              {isTopRecommended && onProceedToApproval && (
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    onClick={() => onProceedToApproval(scen)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 px-3.5 py-2 text-xs font-bold text-white shadow-md shadow-sky-600/20 transition-colors"
                  >
                    <span>Proceed to HITL Cryptographic Approval</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
