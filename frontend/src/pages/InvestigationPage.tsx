/**
 * Investigation Page (P12-3)
 *
 * Dedicated page for multi-agent case investigation and dossier review:
 * - Top enterprise navigation bar with role indicator and status
 * - Main InvestigationPanel layout (Stepper, Narrative, Evidence, Deterministic Math Proof, Mitigation Scenarios)
 */

import React from 'react';
import {
  Activity,
  ArrowLeft,
  User,
} from 'lucide-react';
import { InvestigationPanel } from '../components/InvestigationPanel/InvestigationPanel';

interface InvestigationPageProps {
  onBackToDashboard?: () => void;
  onNavigateToApproval?: (scenario: Record<string, unknown>) => void;
}

export const InvestigationPage: React.FC<InvestigationPageProps> = ({
  onBackToDashboard,
  onNavigateToApproval,
}) => {
  return (
    <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans">
      {/* Top Application Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-[#0c111d]/90 backdrop-blur-md px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {onBackToDashboard && (
            <button
              type="button"
              onClick={onBackToDashboard}
              className="flex items-center gap-1 rounded-lg bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 text-xs text-slate-300 transition-colors border border-slate-700 mr-2"
              title="Return to Risk Dashboard"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Dashboard</span>
            </button>
          )}

          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 shadow-md shadow-sky-500/20">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-white">
                ApexMotion
              </h1>
              <span className="rounded bg-sky-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-400 border border-sky-500/20">
                CASE WORKBENCH
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Multi-Agent Incident Investigation & Sub-90s Forensic Dossier Engine
            </p>
          </div>
        </div>

        {/* Right Header Controls */}
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5 border border-slate-800 text-xs">
            <User className="h-3.5 w-3.5 text-sky-400" />
            <span className="text-slate-400">Role:</span>
            <span className="font-semibold text-slate-200">Supply Chain Analyst</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-6 max-w-[1720px] w-full mx-auto">
        <InvestigationPanel onNavigateToApproval={onNavigateToApproval} />
      </main>
    </div>
  );
};
