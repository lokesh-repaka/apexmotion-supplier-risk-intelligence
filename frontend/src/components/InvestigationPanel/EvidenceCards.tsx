/**
 * Evidence Cards Component (P12-3)
 *
 * Displays multi-modal corroborated evidence:
 * 1. External News & Intelligence (Satellite, Fire Agency, Maritime AIS)
 * 2. Amazon Neptune Multi-Tier Dependency Blast Radius
 * 3. Master Supply Agreement Contract Clauses (§14.2 Force Majeure & Cost-Sharing)
 */

import React from 'react';
import {
  ExternalLink,
  FileText,
  Layers,
  MapPin,
  Radio,
} from 'lucide-react';

interface EvidenceCardsProps {
  researchAnalysis: Record<string, unknown> | null;
  contractAnalysis: Record<string, unknown> | null;
  onCitationClick: (citationTag: string) => void;
}

export const EvidenceCards: React.FC<EvidenceCardsProps> = ({
  researchAnalysis,
  contractAnalysis,
  onCitationClick,
}) => {
  const blastRadius = (researchAnalysis?.blast_radius as Record<string, unknown>) || {};
  const sources = (researchAnalysis?.corroborating_sources as string[]) || [];
  const clauses = (contractAnalysis?.clauses as Array<Record<string, unknown>>) || [];
  const impactedPlants = (blastRadius?.impacted_plants as string[]) || [];
  const impactedPrograms = (blastRadius?.impacted_programs as string[]) || [];

  return (
    <div className="space-y-4">
      {/* 2-Column Grid for Research Intelligence & Blast Radius */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Card 1: Corroborated Signal Feeds */}
        <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-4 shadow-lg space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              <Radio className="h-4 w-4 text-rose-400" />
              <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                External Feeds &middot; Triple-Corroborated
              </h4>
            </div>
            <button
              type="button"
              onClick={() => onCitationClick('REUTERS-TW-9921')}
              className="text-[10px] font-mono text-sky-400 hover:underline flex items-center gap-1"
            >
              <span>[REUTERS-TW-9921]</span>
              <ExternalLink className="h-2.5 w-2.5" />
            </button>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-400">
              <span>Incident Classification:</span>
              <span className="font-semibold text-rose-400">Fab 2 Cleanroom Electrical Fire</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3 text-slate-500" /> Location:
              </span>
              <span className="font-medium text-slate-200">Hsinchu Science Park, Taiwan</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Corroboration Confidence:</span>
              <span className="font-bold text-emerald-400">94.0% (Verified 3/3 Feeds)</span>
            </div>

            <div className="mt-2.5 rounded-lg bg-slate-900/60 p-2.5 border border-slate-800/80">
              <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                Active Telemetry Feeds:
              </span>
              <ul className="space-y-1 text-[11px] text-slate-300">
                {sources.length > 0 ? (
                  sources.map((src, i) => (
                    <li key={`src-${i}`} className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>{src}</span>
                    </li>
                  ))
                ) : (
                  <>
                    <li className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>Taiwan National Fire Agency (NFA-TW)</span>
                    </li>
                    <li className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>NOAA Satellite Thermal Imagery #SAT-9921</span>
                    </li>
                    <li className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>MarineTraffic AIS Telemetry</span>
                    </li>
                  </>
                )}
              </ul>
            </div>
          </div>
        </div>

        {/* Card 2: Neptune Multi-Tier Graph Blast Radius */}
        <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-4 shadow-lg space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-sky-400" />
              <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                Neptune Graph Blast Radius
              </h4>
            </div>
            <button
              type="button"
              onClick={() => onCitationClick('NEPTUNE-GRAPH')}
              className="text-[10px] font-mono text-sky-400 hover:underline flex items-center gap-1"
            >
              <span>[NEPTUNE-GRAPH]</span>
              <ExternalLink className="h-2.5 w-2.5" />
            </button>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-400">
              <span>Root Supplier:</span>
              <span className="font-semibold text-slate-200">NanoCore Microelectronics (Tier-2)</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Direct Tier-1 Customer:</span>
              <span className="font-medium text-sky-300">BetaElectro GmbH</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Impacted Component:</span>
              <span className="font-mono text-amber-300">MCU-X91 &rarr; BMS-E4 Battery Unit</span>
            </div>

            <div className="mt-2.5 space-y-2">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                  Impacted Assembly Plants:
                </span>
                <div className="flex flex-wrap gap-1">
                  {(impactedPlants.length > 0
                    ? impactedPlants
                    : ['Munich Plant (DE)', 'Bengaluru EV (IN)', 'Pune Facility (IN)']
                  ).map((plant, idx) => (
                    <span
                      key={`plant-${idx}`}
                      className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-300 border border-slate-700"
                    >
                      {plant}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                  Impacted Vehicle Programs:
                </span>
                <div className="flex flex-wrap gap-1">
                  {(impactedPrograms.length > 0
                    ? impactedPrograms
                    : ['Model-X Performance EV', 'Hyper-GT Dual-Motor']
                  ).map((prog, idx) => (
                    <span
                      key={`prog-${idx}`}
                      className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-500/20"
                    >
                      {prog}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Card 3: Extracted Master Agreement Intelligence (§14.2 Summary) */}
      <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-4 shadow-lg space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-emerald-400" />
            <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Extracted Legal Contract Intelligence &middot; MSA-2024-BE
            </h4>
          </div>
          <button
            type="button"
            onClick={() => onCitationClick('MSA-2024-BE §14.2')}
            className="text-[10px] font-mono text-sky-400 hover:underline flex items-center gap-1"
          >
            <span>[MSA-2024-BE §14.2]</span>
            <ExternalLink className="h-2.5 w-2.5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {clauses.length > 0 ? (
            clauses.map((clause, idx) => (
              <div
                key={`clause-${idx}`}
                className="rounded-lg bg-slate-900/60 p-3 border border-slate-800 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[10px] text-slate-400">
                      Section {String(clause.section || '14.2')}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        String(clause.status || '').includes('DENIED')
                          ? 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
                          : String(clause.status || '').includes('SHARING')
                            ? 'bg-sky-500/15 text-sky-400 border border-sky-500/20'
                            : 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
                      }`}
                    >
                      {String(clause.status || 'ACTIVE')}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-slate-200 mb-1">
                    {String(clause.title || '')}
                  </div>
                </div>
                <p className="text-[11px] text-slate-400 leading-snug mt-1">
                  {String(clause.summary || '')}
                </p>
              </div>
            ))
          ) : (
            <>
              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] text-slate-400">Section 14.2.1</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/20">
                    DENIED
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-200 mb-1">Force Majeure Relief</div>
                <p className="text-[11px] text-slate-400 leading-snug">
                  Denied because approved AML secondary source (MicroChip Global) is available.
                </p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] text-slate-400">Section 14.2.3</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-400 border border-sky-500/20">
                    50/50 SHARING
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-200 mb-1">Air Freight Liability</div>
                <p className="text-[11px] text-slate-400 leading-snug">
                  BetaElectro GmbH is legally bound to absorb 50% of air freight surcharges up to $100k.
                </p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] text-slate-400">Section 18.4</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/20">
                    +3.0%/DAY
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-200 mb-1">Delivery SLA Penalties</div>
                <p className="text-[11px] text-slate-400 leading-snug">
                  Cumulative daily penalty applied for assembly dock receipt delay past agreed schedule.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
