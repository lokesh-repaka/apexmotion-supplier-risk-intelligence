/**
 * Graph Controls Component (P12-5)
 *
 * Interactive controls for knowledge graph visualization:
 * - Search bar with instant node filtering and autofocus.
 * - Multi-mode layout selector (Hierarchical DAG, Spring Force, Radial).
 * - Multi-attribute tier & node type filters.
 * - Failure path tracing toggle.
 * - Canvas zoom & pan reset controls.
 */

import React from 'react';
import {
  AlertTriangle,
  Compass,
  GitBranch,
  Layers,
  Play,
  RotateCcw,
  Search,
  Square,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { type NodeType, useGraphStore } from '../../stores/useGraphStore';

export const GraphControls: React.FC = () => {
  const {
    searchQuery,
    setSearchQuery,
    filterTier,
    setFilterTier,
    filterNodeType,
    setFilterNodeType,
    isPathHighlightActive,
    togglePathHighlight,
    layoutMode,
    setLayoutMode,
    isSimulating,
    setIsSimulating,
    zoom,
    zoomIn,
    zoomOut,
    resetZoom,
  } = useGraphStore();

  return (
    <div className="bg-[#0b1120]/95 backdrop-blur border border-slate-800 rounded-xl p-4 text-xs text-slate-200 shadow-xl space-y-3">
      {/* Top Row: Search and Path Highlighting */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search Input */}
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search node ID, name, SKU, or location..."
            className="w-full bg-[#080d1a] border border-slate-700/80 rounded-lg pl-9 pr-8 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500/30"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              aria-label="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Critical Failure Path Highlight Toggle */}
        <button
          type="button"
          onClick={togglePathHighlight}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg font-semibold border transition-all ${
            isPathHighlightActive
              ? 'bg-rose-950/70 border-rose-500 text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.35)]'
              : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500'
          }`}
        >
          <AlertTriangle className={`w-3.5 h-3.5 ${isPathHighlightActive ? 'text-rose-400' : 'text-slate-400'}`} />
          <span>Failure Path Tracing</span>
          <span
            className={`w-2 h-2 rounded-full ${
              isPathHighlightActive ? 'bg-rose-500 animate-ping' : 'bg-slate-600'
            }`}
          />
        </button>

        {/* Layout Switcher */}
        <div className="flex items-center gap-1 bg-[#080d1a] p-1 border border-slate-700/80 rounded-lg">
          <button
            type="button"
            onClick={() => setLayoutMode('hierarchical')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md font-medium transition-colors ${
              layoutMode === 'hierarchical'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Layered Tier Columns (Hierarchical DAG)"
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Layered DAG</span>
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode('force')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md font-medium transition-colors ${
              layoutMode === 'force'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Interactive Force-Directed Physics"
          >
            <Layers className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Force Simulation</span>
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode('radial')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md font-medium transition-colors ${
              layoutMode === 'radial'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Concentric Blast Radius Rings"
          >
            <Compass className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Radial Rings</span>
          </button>
        </div>

        {/* Zoom & Canvas Reset Controls */}
        <div className="flex items-center gap-1 bg-[#080d1a] p-1 border border-slate-700/80 rounded-lg">
          <button
            type="button"
            onClick={zoomIn}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded"
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={zoomOut}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded"
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <span className="px-1.5 text-[10px] font-mono text-slate-400">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={resetZoom}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded"
            title="Reset Canvas View"
            aria-label="Reset zoom and center view"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Physics Force Toggle (when in force mode) */}
        {layoutMode === 'force' && (
          <button
            type="button"
            onClick={() => setIsSimulating(!isSimulating)}
            className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg font-medium border transition-colors ${
              isSimulating
                ? 'bg-emerald-950/70 border-emerald-500 text-emerald-300'
                : 'bg-slate-900 border-slate-700 text-slate-300'
            }`}
          >
            {isSimulating ? (
              <>
                <Square className="w-3.5 h-3.5 text-emerald-400 fill-emerald-400" />
                <span>Pause Physics</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 text-slate-400" />
                <span>Run Physics</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Bottom Row: Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
        {/* Tier Filter Pills */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-medium mr-1">Tier:</span>
          {(['ALL', 1, 2, 3] as const).map((tier) => (
            <button
              key={tier}
              type="button"
              onClick={() => setFilterTier(tier)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors ${
                filterTier === tier
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {tier === 'ALL' ? 'All Tiers' : `Tier ${tier}`}
            </button>
          ))}
        </div>

        {/* Node Type Filter Pills */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-medium mr-1">Type:</span>
          {(['ALL', 'supplier', 'component', 'plant', 'program'] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilterNodeType(type as 'ALL' | NodeType)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors capitalize ${
                filterNodeType === type
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {type === 'ALL' ? 'All Types' : type}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
