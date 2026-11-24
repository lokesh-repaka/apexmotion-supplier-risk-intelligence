/**
 * Node Detail Drawer Component (P12-5)
 *
 * Sliding/Collapsible side panel inspecting:
 * - Detailed node metadata (BOM specifications, single-source choke points).
 * - Deterministic risk metrics (Days of Cover, Shortage Volume, Exposure).
 * - Upstream / Downstream graph topological neighbors.
 * - Quick investigation actions and blast radius tracing.
 */

import React from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  DollarSign,
  Factory,
  MapPin,
  ShieldAlert,
  X,
  Zap,
} from 'lucide-react';
import { useGraphStore } from '../../stores/useGraphStore';

export interface NodeDetailDrawerProps {
  onNavigateToInvestigation?: (supplierId: string) => void;
}

export const NodeDetailDrawer: React.FC<NodeDetailDrawerProps> = ({
  onNavigateToInvestigation,
}) => {
  const {
    graphData,
    selectedNodeId,
    selectNode,
    criticalPathNodeIds,
    isPathHighlightActive,
    togglePathHighlight,
  } = useGraphStore();

  if (!graphData || !selectedNodeId) return null;

  const node = graphData.nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;

  // Compute upstream and downstream connections
  const incomingEdges = graphData.edges.filter((e) => e.target === node.id);
  const outgoingEdges = graphData.edges.filter((e) => e.source === node.id);

  const upstreamNodes = incomingEdges
    .map((e) => ({
      edge: e,
      node: graphData.nodes.find((n) => n.id === e.source),
    }))
    .filter((item): item is { edge: typeof item.edge; node: NonNullable<typeof item.node> } => Boolean(item.node));

  const downstreamNodes = outgoingEdges
    .map((e) => ({
      edge: e,
      node: graphData.nodes.find((n) => n.id === e.target),
    }))
    .filter((item): item is { edge: typeof item.edge; node: NonNullable<typeof item.node> } => Boolean(item.node));

  const isCriticalPathNode = criticalPathNodeIds.includes(node.id);

  return (
    <aside className="w-full lg:w-[380px] bg-[#080d1a]/95 backdrop-blur border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col space-y-4 max-h-[720px] overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                node.node_type === 'supplier'
                  ? node.tier === 2 && node.status === 'DISRUPTED'
                    ? 'bg-rose-950 text-rose-300 border border-rose-700/50'
                    : node.aml_status
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/50'
                    : 'bg-sky-950 text-sky-300 border border-sky-700/50'
                  : node.node_type === 'component'
                  ? 'bg-indigo-950 text-indigo-300 border border-indigo-700/50'
                  : node.node_type === 'plant'
                  ? 'bg-teal-950 text-teal-300 border border-teal-700/50'
                  : 'bg-amber-950 text-amber-300 border border-amber-700/50'
              }`}
            >
              {node.node_type === 'supplier'
                ? `Tier-${node.tier || 1} Supplier`
                : node.node_type}
            </span>

            {node.country && (
              <span className="flex items-center gap-1 text-[11px] font-mono text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded">
                <MapPin className="w-3 h-3 text-slate-400" />
                {node.country}
              </span>
            )}

            {node.is_single_source && (
              <span className="flex items-center gap-1 text-[10px] font-bold text-amber-300 bg-amber-950/80 border border-amber-600/60 px-1.5 py-0.5 rounded">
                <ShieldAlert className="w-3 h-3 text-amber-400" />
                Single Source
              </span>
            )}
          </div>

          <h3 className="text-base font-bold text-white leading-tight">
            {node.name}
          </h3>
          <p className="text-xs font-mono text-slate-400 mt-0.5">ID: {node.id}</p>
        </div>

        <button
          type="button"
          onClick={() => selectNode(null)}
          className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800"
          aria-label="Close drawer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Disruption Warning or AML Status Banner */}
      {node.disruption_event ? (
        <div className="bg-rose-950/60 border border-rose-500/70 rounded-lg p-3 text-xs text-rose-200 space-y-1.5">
          <div className="flex items-center gap-1.5 font-bold text-rose-300">
            <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
            <span>Active Disruption Event</span>
          </div>
          <p className="text-rose-100 text-[11px] leading-relaxed">
            {node.disruption_event}
          </p>
        </div>
      ) : node.aml_status ? (
        <div className="bg-emerald-950/60 border border-emerald-500/70 rounded-lg p-3 text-xs text-emerald-200 space-y-1.5">
          <div className="flex items-center gap-1.5 font-bold text-emerald-300">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Qualified AML Secondary Source</span>
          </div>
          <p className="text-emerald-100 text-[11px]">
            Fully validated alternate supply stream for {node.alternate_for || 'disrupted components'}.
          </p>
        </div>
      ) : null}

      {/* Location / Description */}
      {node.location && (
        <div className="text-xs text-slate-300 flex items-start gap-2">
          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
          <span>{node.location}</span>
        </div>
      )}

      {node.description && (
        <p className="text-xs text-slate-400 leading-relaxed bg-[#060911] p-2.5 rounded-lg border border-slate-800/80">
          {node.description}
        </p>
      )}

      {/* Deterministic Metrics Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {node.risk_score !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Composite Risk</div>
            <div className="text-sm font-bold text-white mt-0.5 flex items-center gap-1.5">
              <span>{Number(node.risk_score).toFixed(2)}</span>
              {node.risk_level && (
                <span
                  className={`text-[10px] px-1 py-0.5 rounded font-mono ${
                    node.risk_level === 'CRITICAL'
                      ? 'bg-rose-950 text-rose-400'
                      : node.risk_level === 'HIGH'
                      ? 'bg-amber-950 text-amber-400'
                      : 'bg-emerald-950 text-emerald-400'
                  }`}
                >
                  {node.risk_level}
                </span>
              )}
            </div>
          </div>
        )}

        {node.days_of_cover !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Days of Cover</div>
            <div className="text-sm font-bold text-amber-400 mt-0.5 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              <span>{node.days_of_cover.toFixed(2)} days</span>
            </div>
          </div>
        )}

        {node.financial_exposure !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Exposure USD</div>
            <div className="text-sm font-bold text-rose-400 mt-0.5 flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5" />
              <span>${Number(node.financial_exposure).toLocaleString()}</span>
            </div>
          </div>
        )}

        {node.halt_rate_eur_per_hr !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Line Halt Exposure</div>
            <div className="text-sm font-bold text-rose-400 mt-0.5 flex items-center gap-1">
              <Factory className="w-3.5 h-3.5" />
              <span>€{node.halt_rate_eur_per_hr.toLocaleString()}/hr</span>
            </div>
          </div>
        )}

        {node.unit_cost !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Unit Cost</div>
            <div className="text-sm font-semibold text-slate-200 mt-0.5">
              ${Number(node.unit_cost).toFixed(2)}
            </div>
          </div>
        )}

        {node.lead_time_days !== undefined && (
          <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Lead Time</div>
            <div className="text-sm font-semibold text-slate-200 mt-0.5">
              {node.lead_time_days} days
            </div>
          </div>
        )}

        {node.line_affected && (
          <div className="col-span-2 bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400 font-medium">Affected Assembly Line</div>
            <div className="text-xs font-semibold text-slate-200 mt-0.5">
              {node.line_affected}
            </div>
          </div>
        )}
      </div>

      {/* Upstream Dependencies */}
      <div className="space-y-2 border-t border-slate-800/80 pt-3">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
          <div className="flex items-center gap-1.5">
            <ArrowUpRight className="w-3.5 h-3.5 text-sky-400" />
            <span>Upstream Feeders ({upstreamNodes.length})</span>
          </div>
        </div>

        {upstreamNodes.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic">No upstream dependencies recorded in subgraph.</p>
        ) : (
          <div className="space-y-1.5">
            {upstreamNodes.map(({ edge, node: upNode }) => (
              <button
                key={upNode.id}
                type="button"
                onClick={() => selectNode(upNode.id)}
                className="w-full text-left bg-[#0b1222] hover:bg-slate-800/80 p-2 rounded border border-slate-800/80 flex items-center justify-between transition-colors group"
              >
                <div>
                  <div className="text-xs font-medium text-slate-200 group-hover:text-sky-300">
                    {upNode.name}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">
                    {edge.relationship} &bull; {upNode.id}
                  </div>
                </div>
                <span className="text-[10px] text-sky-400 font-mono">Inspect &rarr;</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Downstream Blast Radius */}
      <div className="space-y-2 border-t border-slate-800/80 pt-3">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
          <div className="flex items-center gap-1.5">
            <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
            <span>Downstream Consumers ({downstreamNodes.length})</span>
          </div>
        </div>

        {downstreamNodes.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic">No downstream dependencies recorded in subgraph.</p>
        ) : (
          <div className="space-y-1.5">
            {downstreamNodes.map(({ edge, node: downNode }) => (
              <button
                key={downNode.id}
                type="button"
                onClick={() => selectNode(downNode.id)}
                className="w-full text-left bg-[#0b1222] hover:bg-slate-800/80 p-2 rounded border border-slate-800/80 flex items-center justify-between transition-colors group"
              >
                <div>
                  <div className="text-xs font-medium text-slate-200 group-hover:text-rose-300">
                    {downNode.name}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">
                    {edge.relationship} &bull; {downNode.id}
                  </div>
                </div>
                <span className="text-[10px] text-rose-400 font-mono">Inspect &rarr;</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="pt-3 border-t border-slate-800/80 space-y-2">
        {isCriticalPathNode && !isPathHighlightActive && (
          <button
            type="button"
            onClick={togglePathHighlight}
            className="w-full flex items-center justify-center gap-2 bg-rose-950/60 hover:bg-rose-900 border border-rose-600/70 text-rose-200 px-3 py-2 rounded-lg text-xs font-semibold transition-colors"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
            <span>Trace Critical Failure Path</span>
          </button>
        )}

        {node.node_type === 'supplier' && onNavigateToInvestigation && (
          <button
            type="button"
            onClick={() => onNavigateToInvestigation(node.id)}
            className="w-full flex items-center justify-center gap-2 bg-sky-600 hover:bg-sky-500 text-white px-3 py-2 rounded-lg text-xs font-semibold transition-colors shadow-sm"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>Investigate in Dossier</span>
          </button>
        )}
      </div>
    </aside>
  );
};
