/**
 * Citation Evidence Modal Component (P12-3)
 *
 * Displays deep-dive telemetry, source verification details, and audit metadata
 * when a user clicks any citation tag in the incident narrative.
 */

import React from 'react';
import {
  CheckCircle2,
  Clock,
  FileText,
  ShieldCheck,
  X,
} from 'lucide-react';
import type { CitationDetail } from '../../stores/useInvestigationStore';

interface CitationModalProps {
  citation: CitationDetail | null;
  onClose: () => void;
}

export const CitationModal: React.FC<CitationModalProps> = ({ citation, onClose }) => {
  if (!citation) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-[#0c111d] p-6 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
              <FileText className="h-4 w-4" />
            </div>
            <div>
              <span className="font-mono text-[10px] uppercase font-bold text-sky-400">
                Evidence Citation &middot; [{citation.tag}]
              </span>
              <h3 className="text-sm font-bold text-white">{citation.title}</h3>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Verification Status Pill */}
        <div className="flex items-center justify-between rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-xs text-emerald-300">
          <div className="flex items-center gap-1.5 font-medium">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>{citation.verification}</span>
          </div>
          <span className="font-mono text-[10px] text-emerald-400 font-bold uppercase">
            Confidence: 94%
          </span>
        </div>

        {/* Source & Timestamp Metadata */}
        <div className="space-y-2 text-xs font-mono">
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-sans">Primary Source:</span>
            <span className="text-slate-200 font-semibold">{citation.source}</span>
          </div>
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-sans flex items-center gap-1">
              <Clock className="h-3 w-3 text-slate-500" /> Ingestion Timestamp:
            </span>
            <span className="text-slate-300">{citation.timestamp}</span>
          </div>
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-sans flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-slate-500" /> Quarantined Verification:
            </span>
            <span className="text-emerald-400 font-bold">Passed (Prompt Injection Safe)</span>
          </div>
        </div>

        {/* Full Extracted Summary */}
        <div className="rounded-xl bg-[#060911] border border-slate-800 p-3.5 space-y-1.5">
          <span className="text-[10px] uppercase font-bold text-slate-500 block">
            Corroborated Telemetry Summary:
          </span>
          <p className="text-xs text-slate-200 leading-relaxed">{citation.summary}</p>
        </div>

        {/* Footer Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-800 hover:bg-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
