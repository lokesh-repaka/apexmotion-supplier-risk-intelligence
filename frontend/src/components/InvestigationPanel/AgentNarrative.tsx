/**
 * Agent Narrative Component (P12-3)
 *
 * Renders the synthesized multi-agent incident narrative with interactive citation tags.
 * Replaces bracketed citation keys with clickable buttons that open source evidence details.
 */

import React from 'react';
import { ExternalLink, FileText, Sparkles } from 'lucide-react';

interface AgentNarrativeProps {
  narrative: string | null;
  caseId: string;
  isDegradedMode?: boolean;
  onCitationClick: (citationTag: string) => void;
}

// Regex to capture citation tags like [REUTERS-TW-9921], [NEPTUNE-GRAPH], [SAP-INV-001], [MSA-2024-BE §14.2]
const CITATION_REGEX = /\[([A-Z0-9_\-§.\s]+)\]/g;

export const AgentNarrative: React.FC<AgentNarrativeProps> = ({
  narrative,
  caseId,
  isDegradedMode = false,
  onCitationClick,
}) => {
  // Render paragraph with clickable citation tags
  const renderParagraphWithCitations = (text: string, pIndex: number) => {
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    // Reset regex index
    CITATION_REGEX.lastIndex = 0;

    while ((match = CITATION_REGEX.exec(text)) !== null) {
      const matchIndex = match.index;
      const citationTag = match[1];

      // Add text before citation
      if (matchIndex > lastIndex) {
        parts.push(text.substring(lastIndex, matchIndex));
      }

      // Add citation button
      parts.push(
        <button
          key={`cite-${pIndex}-${matchIndex}`}
          type="button"
          onClick={() => onCitationClick(citationTag)}
          className="inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 rounded bg-sky-500/15 hover:bg-sky-500/30 text-sky-400 font-mono text-[11px] font-semibold border border-sky-500/30 transition-colors shadow-sm focus:outline-none focus:ring-1 focus:ring-sky-400"
          title={`View verified evidence citation for [${citationTag}]`}
        >
          <span>[{citationTag}]</span>
          <ExternalLink className="h-2.5 w-2.5 opacity-70" />
        </button>
      );

      lastIndex = CITATION_REGEX.lastIndex;
    }

    // Add trailing text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return (
      <p key={`p-${pIndex}`} className="leading-relaxed text-slate-300 text-xs sm:text-sm">
        {parts}
      </p>
    );
  };

  const paragraphs = (narrative || '').split('\n\n').filter((p) => p.trim().length > 0);

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-5 shadow-lg space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <FileText className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Synthesized Incident Narrative &middot; {caseId}
            </h3>
            <p className="text-[11px] text-slate-400">
              Corroborated Multi-Agent Evidence Synthesis (SLO p95 &le; 90s)
            </p>
          </div>
        </div>

        <span className="inline-flex items-center gap-1.5 rounded-full bg-sky-500/10 px-2.5 py-1 text-[11px] font-semibold text-sky-400 border border-sky-500/20">
          <Sparkles className="h-3 w-3" />
          <span>LangGraph Detective Agent &middot; 100% Grounded</span>
        </span>
      </div>

      {/* Circuit Breaker Fallback Notice */}
      {isDegradedMode && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-950/30 p-3 text-xs text-amber-200 flex items-start gap-2">
          <span className="font-bold text-amber-400 text-sm">⚠️</span>
          <div>
            <strong>CIRCUIT BREAKER ACTIVATED:</strong> LLM Narrative Synthesis timed out.
            Narrative is operating in <strong>Deterministic Fallback Mode (FRD FR-DEC-001 Alt Flow)</strong>.
            Zero numbers or financial metrics are hallucinated.
          </div>
        </div>
      )}

      {/* Narrative Body */}
      {paragraphs.length > 0 ? (
        <div className="space-y-3.5">
          {paragraphs.map((p, idx) => renderParagraphWithCitations(p, idx))}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-8 text-center text-xs text-slate-500">
          No agent narrative synthesized yet. Launch or poll an investigation to generate grounded analysis.
        </div>
      )}

      {/* Grounding Footnote */}
      <div className="border-t border-slate-800/60 pt-3 flex flex-wrap items-center justify-between text-[11px] text-slate-500 gap-2">
        <span>Click any bracketed citation tag above to inspect verified primary source telemetry.</span>
        <span className="font-mono text-emerald-400/90 font-semibold">Zero Generative Math (BR-RULE-001)</span>
      </div>
    </div>
  );
};
