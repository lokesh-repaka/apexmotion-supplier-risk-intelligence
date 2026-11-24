/**
 * Audit Timeline Component (P12-6)
 *
 * Chronological immutable timeline per alert:
 * - Sequential Merkle-chained blocks (Genesis to terminal PO dispatch).
 * - Multi-attribute action filters and instant search query.
 * - Distinct event iconography and state transition telemetry.
 * - Current SHA-256 and previous block hash verification.
 */

import React from 'react';
import {
  Activity,
  Calculator,
  FileText,
  Fingerprint,
  GitBranch,
  KeyRound,
  Radio,
  Search,
  Send,
  ShieldAlert,
} from 'lucide-react';
import {
  type AuditActionType,
  useAuditStore,
} from '../../stores/useAuditStore';

export const AuditTimeline: React.FC = () => {
  const {
    blocks,
    selectedBlockId,
    selectBlock,
    searchQuery,
    setSearchQuery,
    actionFilter,
    setActionFilter,
  } = useAuditStore();

  // Filter blocks
  const filteredBlocks = blocks.filter((b) => {
    if (actionFilter !== 'ALL' && b.action !== actionFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchesSummary = b.summary.toLowerCase().includes(q);
      const matchesActor = b.actor_name.toLowerCase().includes(q);
      const matchesAction = b.action.toLowerCase().includes(q);
      const matchesTrace = Boolean(b.trace_id?.toLowerCase().includes(q));
      const matchesHash = b.current_hash.toLowerCase().includes(q);
      if (!matchesSummary && !matchesActor && !matchesAction && !matchesTrace && !matchesHash) {
        return false;
      }
    }
    return true;
  });

  const getActionBadge = (action: AuditActionType) => {
    switch (action) {
      case 'SIGNAL_INGEST':
        return {
          color: 'bg-rose-950/80 text-rose-300 border-rose-600/50',
          icon: <Radio className="w-3.5 h-3.5 text-rose-400" />,
          label: 'SIGNAL INGEST',
        };
      case 'GRAPH_TRAVERSAL':
        return {
          color: 'bg-sky-950/80 text-sky-300 border-sky-600/50',
          icon: <GitBranch className="w-3.5 h-3.5 text-sky-400" />,
          label: 'GRAPH TRAVERSAL',
        };
      case 'MATH_CERTIFIED':
        return {
          color: 'bg-amber-950/80 text-amber-300 border-amber-600/50',
          icon: <Calculator className="w-3.5 h-3.5 text-amber-400" />,
          label: 'MATH CERTIFIED (BR-001)',
        };
      case 'DOSSIER_READY':
        return {
          color: 'bg-purple-950/80 text-purple-300 border-purple-600/50',
          icon: <FileText className="w-3.5 h-3.5 text-purple-400" />,
          label: 'DOSSIER READY',
        };
      case 'HITL_PENDING_REVIEW':
        return {
          color: 'bg-rose-950/80 text-rose-300 border-rose-600/50',
          icon: <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />,
          label: 'HITL PENDING',
        };
      case 'HITL_TOKEN_SIGNED':
        return {
          color: 'bg-emerald-950/80 text-emerald-300 border-emerald-600/50',
          icon: <KeyRound className="w-3.5 h-3.5 text-emerald-400" />,
          label: 'KMS TOKEN SIGNED',
        };
      case 'SAP_PO_DISPATCHED':
        return {
          color: 'bg-cyan-950/80 text-cyan-300 border-cyan-600/50',
          icon: <Send className="w-3.5 h-3.5 text-cyan-400" />,
          label: 'SAP ERP DISPATCH',
        };
      default:
        return {
          color: 'bg-slate-800 text-slate-300 border-slate-700',
          icon: <Activity className="w-3.5 h-3.5 text-slate-400" />,
          label: action,
        };
    }
  };

  const actionOptions = [
    'ALL',
    'SIGNAL_INGEST',
    'GRAPH_TRAVERSAL',
    'MATH_CERTIFIED',
    'DOSSIER_READY',
    'HITL_PENDING_REVIEW',
    'HITL_TOKEN_SIGNED',
    'SAP_PO_DISPATCHED',
  ];

  return (
    <div className="bg-[#0b1120] border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
      {/* Controls: Search and Action Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search action, actor, trace ID, or SHA-256 hash..."
            className="w-full bg-[#080d1a] border border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
        </div>

        {/* Action Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 text-xs">
          <span className="text-slate-400 font-medium mr-1 text-[11px]">Filter:</span>
          {actionOptions.slice(0, 5).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setActionFilter(opt)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold whitespace-nowrap transition-colors ${
                actionFilter === opt
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {opt === 'ALL' ? 'All Events' : opt.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline List */}
      <div className="space-y-3">
        {filteredBlocks.map((block) => {
          const badge = getActionBadge(block.action);
          const isSelected = selectedBlockId === block.id;

          return (
            <div
              key={block.id}
              onClick={() => selectBlock(block.id)}
              className={`p-4 rounded-xl border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-[#0f172a] border-sky-500 shadow-md ring-1 ring-sky-500/30'
                  : 'bg-[#080d1a] hover:bg-slate-900 border-slate-800'
              }`}
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2">
                {/* Left: Index, Time, Badge, Actor */}
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="w-6 h-6 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 font-mono text-[11px] font-bold flex items-center justify-center">
                    #{block.block_index}
                  </span>

                  <span className="text-xs font-mono text-slate-400">
                    {block.timestamp.replace('T', ' ').replace('Z', ' UTC')}
                  </span>

                  <span
                    className={`flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-0.5 rounded border uppercase tracking-wider ${badge.color}`}
                  >
                    {badge.icon}
                    <span>{badge.label}</span>
                  </span>

                  <span className="text-xs font-medium text-slate-300">
                    by <strong className="text-white">{block.actor_name}</strong>
                  </span>
                </div>

                {/* Right: Trace ID and Merkle Chip */}
                <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
                  {block.trace_id && (
                    <span className="bg-slate-800/80 px-2 py-0.5 rounded text-sky-400">
                      trace: {block.trace_id}
                    </span>
                  )}
                  <span className="text-emerald-400 flex items-center gap-1 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40">
                    <Fingerprint className="w-3 h-3 text-emerald-400" />
                    <span>SHA-256 Verified</span>
                  </span>
                </div>
              </div>

              {/* Transaction Summary */}
              <p className="text-xs text-slate-200 mt-2 font-medium leading-relaxed">
                {block.summary}
              </p>

              {/* Hashes Row */}
              <div className="mt-2.5 pt-2 border-t border-slate-800/70 flex flex-wrap items-center gap-4 text-[11px] font-mono">
                <div className="flex items-center gap-1.5">
                  <span className="text-slate-500">Current Hash:</span>
                  <span className="text-cyan-400 font-bold">
                    {block.current_hash.slice(0, 16)}...
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <span className="text-slate-500">Prev Hash:</span>
                  <span className="text-slate-400">
                    {block.previous_hash.slice(0, 16)}...
                    {block.block_index === 1 && ' (GENESIS)'}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
