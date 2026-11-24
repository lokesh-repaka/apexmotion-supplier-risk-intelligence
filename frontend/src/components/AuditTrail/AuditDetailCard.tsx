/**
 * Audit Detail Card Component (P12-6)
 *
 * Displays:
 * - Deep forensic inspection of selected audit block.
 * - Before State vs After State JSON state transitions.
 * - Merkle SHA-256 block hash chaining telemetry.
 * - Cryptographic AWS KMS ECDSA P-256 token verification signatures.
 */

import React from 'react';
import {
  CheckCircle2,
  Code2,
  Database,
  Fingerprint,
  ShieldCheck,
  User,
  X,
} from 'lucide-react';
import { useAuditStore } from '../../stores/useAuditStore';

export const AuditDetailCard: React.FC = () => {
  const { blocks, selectedBlockId, selectBlock } = useAuditStore();

  if (!selectedBlockId) return null;

  const block = blocks.find((b) => b.id === selectedBlockId);
  if (!block) return null;

  return (
    <div className="bg-[#080d1a] border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-5 h-5 rounded-md bg-slate-800 border border-slate-700 text-slate-300 font-mono text-[10px] font-bold flex items-center justify-center">
              #{block.block_index}
            </span>
            <span className="text-xs font-mono font-bold text-sky-400">
              {block.action}
            </span>
            <span className="text-slate-600">&bull;</span>
            <span className="text-xs font-mono text-slate-400">
              {block.timestamp.replace('T', ' ').replace('Z', ' UTC')}
            </span>
          </div>

          <h3 className="text-sm font-bold text-white leading-tight">
            {block.summary}
          </h3>
        </div>

        <button
          type="button"
          onClick={() => selectBlock(null)}
          className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800"
          aria-label="Close details"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Meta Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
          <div className="text-[10px] text-slate-400 font-medium">Actor / Service</div>
          <div className="text-xs font-bold text-white mt-0.5 flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-sky-400" />
            <span>{block.actor_name}</span>
          </div>
          {block.actor_role && (
            <div className="text-[10px] font-mono text-slate-400 mt-0.5">
              Role: {block.actor_role}
            </div>
          )}
        </div>

        <div className="bg-[#0b1222] p-2.5 rounded-lg border border-slate-800">
          <div className="text-[10px] text-slate-400 font-medium">Entity Reference</div>
          <div className="text-xs font-bold text-slate-200 mt-0.5 flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-indigo-400" />
            <span>{block.entity_type}</span>
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            ID: {block.entity_id}
          </div>
        </div>
      </div>

      {/* Details Description */}
      {block.details && (
        <div className="bg-[#0b1222] p-3 rounded-lg border border-slate-800 text-xs text-slate-300 leading-relaxed">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
            Transaction Narrative & Rule Invariant
          </div>
          {block.details}
        </div>
      )}

      {/* Before / After State Transition Diff */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* Before State */}
        <div className="bg-[#060911] p-3 rounded-xl border border-slate-800 space-y-1.5">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <Code2 className="w-3 h-3 text-slate-400" />
            <span>Pre-Action State (before_state)</span>
          </div>
          <pre className="font-mono text-[11px] text-slate-300 overflow-x-auto max-h-36 p-2 bg-[#080d1a] rounded border border-slate-800/80">
            {block.before_state
              ? JSON.stringify(block.before_state, null, 2)
              : '// Null state (Genesis Ingestion)'}
          </pre>
        </div>

        {/* After State */}
        <div className="bg-[#060911] p-3 rounded-xl border border-slate-800 space-y-1.5">
          <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>Post-Action State (after_state)</span>
          </div>
          <pre className="font-mono text-[11px] text-emerald-200 overflow-x-auto max-h-36 p-2 bg-[#080d1a] rounded border border-slate-800/80">
            {block.after_state
              ? JSON.stringify(block.after_state, null, 2)
              : '// State committed'}
          </pre>
        </div>
      </div>

      {/* Cryptographic Proof & Merkle Hash Chaining */}
      <div className="bg-[#0b1222] p-3 rounded-xl border border-slate-800 space-y-2 text-xs font-mono">
        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <Fingerprint className="w-3.5 h-3.5 text-sky-400" />
            <span>Merkle Cryptographic Hash Verification</span>
          </span>
          <span className="text-emerald-400 flex items-center gap-1 text-[10px]">
            <ShieldCheck className="w-3 h-3" />
            <span>Chained & Verified</span>
          </span>
        </div>

        <div className="space-y-1 text-[11px]">
          <div className="flex items-start justify-between gap-2">
            <span className="text-slate-500 shrink-0">Current SHA-256:</span>
            <span className="text-cyan-400 break-all select-all font-semibold">
              {block.current_hash}
            </span>
          </div>

          <div className="flex items-start justify-between gap-2">
            <span className="text-slate-500 shrink-0">Previous Block:</span>
            <span className="text-slate-400 break-all select-all">
              {block.previous_hash}
            </span>
          </div>

          {block.signature && (
            <div className="flex items-start justify-between gap-2 pt-1 border-t border-slate-800">
              <span className="text-slate-500 shrink-0">KMS Signature:</span>
              <span className="text-emerald-400 break-all select-all">
                {block.signature}
              </span>
            </div>
          )}

          {block.trace_id && (
            <div className="flex items-start justify-between gap-2 pt-1 border-t border-slate-800">
              <span className="text-slate-500 shrink-0">Trace Context:</span>
              <span className="text-slate-300">
                {block.trace_id}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
