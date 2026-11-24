/**
 * Graph Legend Component (P12-5)
 *
 * Visual guide explaining:
 * - Multi-tier supplier node categories (Tier 1, Tier 2, Tier 3, AML Alternate).
 * - Component, Plant, and Vehicle Program nodes.
 * - Disrupted failure paths vs qualified alternate paths.
 */

import React from 'react';
import { Layers } from 'lucide-react';

export const GraphLegend: React.FC = () => {
  return (
    <div className="bg-[#0b1120]/90 backdrop-blur border border-slate-800 rounded-xl p-3.5 text-xs text-slate-300 shadow-xl space-y-3">
      <div className="flex items-center gap-2 font-semibold text-slate-200 border-b border-slate-800/80 pb-2">
        <Layers className="w-3.5 h-3.5 text-sky-400" />
        <span>Graph Legend & Topology Key</span>
      </div>

      {/* Node Categories */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-rose-600 ring-2 ring-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.6)]" />
          <span className="text-[11px]">Tier-2 (Disrupted)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-emerald-600 ring-2 ring-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
          <span className="text-[11px]">Tier-2 (AML Qualified)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-sky-600 ring-2 ring-sky-400" />
          <span className="text-[11px]">Tier-1 Integrator</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-slate-600 ring-2 ring-slate-400" />
          <span className="text-[11px]">Tier-3 Raw Materials</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3.5 h-3 rounded bg-indigo-900 border border-indigo-400" />
          <span className="text-[11px]">Component / Part SKU</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3.5 h-3 rounded-md bg-teal-900 border border-teal-400" />
          <span className="text-[11px]">Assembly Plant</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rotate-45 bg-amber-600 ring-1 ring-amber-300" />
          <span className="text-[11px]">Vehicle Program</span>
        </div>
      </div>

      {/* Edge Categories */}
      <div className="border-t border-slate-800/80 pt-2 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <div className="flex items-center gap-2">
          <span className="w-6 h-0.5 border-t-2 border-dashed border-rose-500" />
          <span>Critical Failure Path</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-6 h-0.5 border-t-2 border-dashed border-emerald-400" />
          <span>AML Alternate Route</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-6 h-0.5 bg-slate-600" />
          <span>Standard Dependency</span>
        </div>
      </div>
    </div>
  );
};
