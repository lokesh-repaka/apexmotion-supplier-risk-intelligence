/**
 * Supplier Graph Visualizer Page (P12-5)
 *
 * Assembles:
 * - Amazon Neptune OpenCypher 2-hop topological ego-subgraph visualization.
 * - Interactive Canvas/SVG force-directed and layered DAG graph renderer.
 * - Multi-attribute topology controls (Tier, Node Type, Search, Critical Path Tracing).
 * - Node inspection drawer with deterministic risk and BOM metrics.
 * - Seamless walkthrough navigation between Dashboard, Graph, and Investigation.
 */

import React, { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ChevronDown,
  Network,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import {
  GraphControls,
  GraphLegend,
  NodeDetailDrawer,
  SupplierGraphVisualiser,
} from '../components/SupplierGraph';
import { useGraphStore } from '../stores/useGraphStore';

export interface SupplierGraphPageProps {
  onNavigateToInvestigation?: (supplierId?: string) => void;
  onBackToDashboard?: () => void;
}

const PRESET_SUPPLIERS = [
  { id: 'SUP-NC-001', name: 'NanoCore Microelectronics (Disrupted Fab 2)', tier: 2 },
  { id: 'SUP-BETA-001', name: 'BetaElectro GmbH (Tier-1 Integrator)', tier: 1 },
  { id: 'SUP-MC-002', name: 'MicroChip Global (Qualified AML Secondary)', tier: 2 },
  { id: 'SUP-FORMOSA-003', name: 'Formosa Semiconductor (Tier-3 Silicon)', tier: 3 },
];

export const SupplierGraphPage: React.FC<SupplierGraphPageProps> = ({
  onNavigateToInvestigation,
  onBackToDashboard,
}) => {
  const {
    currentSupplierId,
    graphData,
    isLoading,
    fetchSupplierGraph,
    loadCanonicalGraph,
  } = useGraphStore();

  const [selectedPreset, setSelectedPreset] = useState(currentSupplierId || 'SUP-NC-001');

  useEffect(() => {
    if (!graphData) {
      loadCanonicalGraph();
    }
  }, [graphData, loadCanonicalGraph]);

  const handleSupplierChange = (id: string) => {
    setSelectedPreset(id);
    fetchSupplierGraph(id);
  };

  return (
    <div className="p-6 max-w-[1720px] w-full mx-auto space-y-5">
      {/* Page Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-[#080d1a] border border-slate-800 rounded-2xl p-5 shadow-lg">
        <div>
          <div className="flex items-center gap-2 mb-1">
            {onBackToDashboard && (
              <button
                type="button"
                onClick={onBackToDashboard}
                className="text-xs text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1 mr-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Dashboard</span>
              </button>
            )}
            <span className="bg-sky-950/80 border border-sky-600/50 text-sky-300 text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase tracking-wider flex items-center gap-1.5">
              <Network className="w-3 h-3 text-sky-400" />
              Amazon Neptune OpenCypher
            </span>
            <span className="text-slate-500 text-xs">&bull;</span>
            <span className="text-slate-400 text-xs font-mono">
              400k Nodes &bull; 3M Edges Graph Fabric
            </span>
          </div>

          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Multi-Tier Dependency & Blast Radius Visualiser
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Interactive 2-hop topological ego-subgraph tracing single-source component dependencies, tier propagation, and vehicle assembly line halts.
          </p>
        </div>

        {/* Telemetry and Supplier Preset Selector */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Preset Selector */}
          <div className="relative">
            <select
              value={selectedPreset}
              onChange={(e) => handleSupplierChange(e.target.value)}
              className="appearance-none bg-[#0b1222] border border-slate-700 rounded-xl pl-3 pr-8 py-2 text-xs text-slate-200 font-medium focus:outline-none focus:border-sky-500 cursor-pointer shadow-sm"
            >
              {PRESET_SUPPLIERS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}: {s.name}
                </option>
              ))}
            </select>
            <ChevronDown className="w-4 h-4 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Refresh Subgraph Button */}
          <button
            type="button"
            onClick={() => fetchSupplierGraph(selectedPreset)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold border border-slate-700/80 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-sky-400' : ''}`} />
            <span>{isLoading ? 'Traversing...' : 'Refresh Subgraph'}</span>
          </button>

          {/* Jump to Investigation Dossier */}
          {onNavigateToInvestigation && (
            <button
              type="button"
              onClick={() => onNavigateToInvestigation(selectedPreset)}
              className="flex items-center gap-1.5 px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold transition-colors shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Investigate Dossier</span>
            </button>
          )}
        </div>
      </div>

      {/* Graph Visualizer Controls */}
      <GraphControls />

      {/* Main Workspace Grid: Canvas + Node Detail Drawer */}
      <div className="flex flex-col lg:flex-row gap-5 items-start">
        {/* Graph Canvas */}
        <div className="flex-1 w-full">
          <SupplierGraphVisualiser />
        </div>

        {/* Node Detail Drawer */}
        <NodeDetailDrawer
          onNavigateToInvestigation={(id) => onNavigateToInvestigation?.(id)}
        />
      </div>

      {/* Bottom Legend */}
      <GraphLegend />
    </div>
  );
};
