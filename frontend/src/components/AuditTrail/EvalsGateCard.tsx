/**
 * CI/CD Continuous Evals Gate & Business Rules Card (P12-6)
 *
 * Implements:
 * - Automated CI/CD Regression Evaluation Gate (FRD FR-GOV-002).
 * - Live performance metrics (Entity F1, Graph Accuracy, Math Consistency, Citation Score).
 * - 7 Core Enforced Business Rules Chips (FRD §3 / BR-001 to BR-007).
 */

import React from 'react';
import {
  CheckCircle2,
  Scale,
} from 'lucide-react';
import {
  CONTINUOUS_EVALS_METRICS,
  ENFORCED_BUSINESS_RULES,
} from '../../stores/useAuditStore';

export const EvalsGateCard: React.FC = () => {
  return (
    <div className="bg-[#080d1a] border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/80 border border-emerald-600/50 px-2 py-0.5 rounded">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              Automated Evaluation Gate
            </span>
            <span className="text-slate-600 text-xs">&bull;</span>
            <span className="text-slate-400 text-xs font-mono">
              CI/CD Regression Baseline (FRD FR-GOV-002)
            </span>
          </div>

          <h3 className="text-base font-bold text-white tracking-tight">
            Continuous Governance & Model Evaluation Benchmarks
          </h3>
        </div>

        <div className="flex items-center gap-2 bg-emerald-950/70 border border-emerald-500/60 text-emerald-300 px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>GATE: PASS &check;</span>
        </div>
      </div>

      {/* 4 Evals Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        {CONTINUOUS_EVALS_METRICS.map((metric) => (
          <div
            key={metric.name}
            className="bg-[#0b1120] p-3 rounded-xl border border-slate-800 space-y-1"
          >
            <div className="text-[10px] font-semibold text-slate-400">
              {metric.name}
            </div>
            <div className="text-lg font-black text-emerald-400">
              {metric.value}
            </div>
            <div className="text-[10px] font-mono text-slate-500">
              {metric.target}
            </div>
          </div>
        ))}
      </div>

      {/* 7 Core Business Rules Chips */}
      <div className="pt-2 border-t border-slate-800/80 space-y-2">
        <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
          <Scale className="w-3.5 h-3.5 text-sky-400" />
          <span>Enforced Platform Business Rules (FRD §3)</span>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          {ENFORCED_BUSINESS_RULES.map((rule) => (
            <div
              key={rule.id}
              className="bg-[#0b1222] border border-slate-800 hover:border-slate-700 px-3 py-1.5 rounded-lg flex items-center gap-2 transition-colors group"
              title={rule.desc}
            >
              <span className="font-mono text-[10px] font-bold text-sky-400">
                {rule.id}
              </span>
              <span className="text-[11px] font-medium text-slate-300 group-hover:text-white">
                {rule.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
