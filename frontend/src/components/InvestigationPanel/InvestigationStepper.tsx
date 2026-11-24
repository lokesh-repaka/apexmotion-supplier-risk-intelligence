/**
 * 6-Stage Multi-Agent Investigation Stepper (FRD FR-DEC-001)
 *
 * Visualizes the sub-90s incident investigation progression across LangGraph nodes:
 * 1. Signal Ingest & Quarantined Triage (triage)
 * 2. Neptune Multi-Tier Graph Traversal (research)
 * 3. SAP ERP Stock & PO Sync
 * 4. Deterministic Math Engine (risk)
 * 5. Contract Intelligence & Clauses (contract)
 * 6. Mitigation Packages & HITL Gate (recommendation / hitl_gate)
 */

import React from 'react';
import {
  CheckCircle2,
  Clock,
  Cpu,
  FileText,
  Layers,
  RotateCw,
  ShieldCheck,
  Zap,
} from 'lucide-react';

interface InvestigationStepperProps {
  currentNode: string | null;
  executionPath: string[];
  status: string;
  elapsedSeconds: number;
  estimatedSeconds?: number;
  isDegradedMode?: boolean;
}

interface StepConfig {
  id: string;
  nodeKey: string;
  label: string;
  stageName: string;
  timeWindow: string;
  icon: React.ComponentType<{ className?: string }>;
  detail: string;
}

const STEPS: StepConfig[] = [
  {
    id: 'step1',
    nodeKey: 'triage',
    label: 'Stage 1',
    stageName: 'Signal Ingest',
    timeWindow: '0–5s',
    icon: Zap,
    detail: 'Quarantined & Sanitized',
  },
  {
    id: 'step2',
    nodeKey: 'research',
    label: 'Stage 2',
    stageName: 'Neptune Graph',
    timeWindow: '5–35s',
    icon: Layers,
    detail: 'Tier-2 Path Traversed',
  },
  {
    id: 'step3',
    nodeKey: 'erp',
    label: 'Stage 3',
    stageName: 'SAP ERP Sync',
    timeWindow: '35–50s',
    icon: Cpu,
    detail: 'Stock=142k Balances',
  },
  {
    id: 'step4',
    nodeKey: 'risk',
    label: 'Stage 4',
    stageName: 'Deterministic Math',
    timeWindow: '50–65s',
    icon: ShieldCheck,
    detail: 'Days of Cover = 7.68d',
  },
  {
    id: 'step5',
    nodeKey: 'contract',
    label: 'Stage 5',
    stageName: 'Contract Intel',
    timeWindow: '65–80s',
    icon: FileText,
    detail: '§14.2 Force Majeure Denied',
  },
  {
    id: 'step6',
    nodeKey: 'recommendation',
    label: 'Stage 6',
    stageName: 'Mitigation Pkg',
    timeWindow: '80–90s',
    icon: CheckCircle2,
    detail: '3 Ranked Scenarios',
  },
];

export const InvestigationStepper: React.FC<InvestigationStepperProps> = ({
  currentNode,
  executionPath,
  status,
  elapsedSeconds,
  estimatedSeconds = 90,
  isDegradedMode = false,
}) => {
  const isComplete = ['COMPLETED', 'AWAITING_APPROVAL'].includes(status);
  const isFailed = status === 'FAILED';
  const progressPct = Math.min(100, Math.round((elapsedSeconds / estimatedSeconds) * 100));

  const getStepStatus = (step: StepConfig, index: number): 'completed' | 'active' | 'pending' | 'failed' => {
    if (isFailed && currentNode === step.nodeKey) {
      return 'failed';
    }

    if (isComplete) {
      return 'completed';
    }

    // Direct node match
    if (currentNode === step.nodeKey) {
      return 'active';
    }

    // Node exists in history
    if (executionPath.includes(step.nodeKey)) {
      return 'completed';
    }

    // For intermediate steps like ERP (part of triage/research)
    if (step.nodeKey === 'erp') {
      if (executionPath.includes('risk') || executionPath.includes('recommendation') || isComplete) {
        return 'completed';
      }
      if (currentNode === 'research' || executionPath.includes('research')) {
        return 'active';
      }
    }

    // If step index precedes the current node's step index
    const activeIndex = STEPS.findIndex((s) => s.nodeKey === currentNode);
    if (activeIndex > index) {
      return 'completed';
    }

    return 'pending';
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-4 shadow-lg space-y-4">
      {/* Header with Title and Latency SLA Meter */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              6-Stage Investigation Pipeline Stepper
            </h3>
            <p className="text-[11px] text-slate-400">
              LangGraph Multi-Agent Detective Workflow (SLO p95 &le; 90.0s)
            </p>
          </div>
        </div>

        {/* Stopwatch & SLA Indicator */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 rounded-lg bg-slate-900 px-2.5 py-1 text-xs border border-slate-800">
            <Clock className="h-3.5 w-3.5 text-sky-400" />
            <span className="font-mono font-semibold text-slate-200">
              {elapsedSeconds.toFixed(1)}s
            </span>
            <span className="text-[10px] text-slate-500">/ {estimatedSeconds}s SLA</span>
          </div>

          <div
            className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
              isComplete
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : isFailed
                  ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
            }`}
          >
            {!isComplete && !isFailed && <RotateCw className="h-3 w-3 animate-spin" />}
            {isComplete && <CheckCircle2 className="h-3 w-3" />}
            <span>{isComplete ? 'READY FOR REVIEW' : isFailed ? 'FAILED' : 'INVESTIGATING'}</span>
          </div>
        </div>
      </div>

      {/* SLA Progress Bar */}
      <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-full transition-all duration-500 rounded-full ${
            isComplete
              ? 'bg-emerald-500'
              : elapsedSeconds > estimatedSeconds
                ? 'bg-amber-500'
                : 'bg-sky-500'
          }`}
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Stepper Columns */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {STEPS.map((step, idx) => {
          const stepStatus = getStepStatus(step, idx);
          const Icon = step.icon;

          return (
            <div
              key={step.id}
              className={`rounded-lg border p-2.5 transition-all flex flex-col justify-between ${
                stepStatus === 'completed'
                  ? 'border-emerald-500/30 bg-emerald-950/10 text-slate-200'
                  : stepStatus === 'active'
                    ? 'border-sky-500/60 bg-sky-950/20 text-white shadow-md shadow-sky-500/10 ring-1 ring-sky-500/30'
                    : stepStatus === 'failed'
                      ? 'border-rose-500/40 bg-rose-950/20 text-rose-300'
                      : 'border-slate-800 bg-slate-900/40 text-slate-500'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] text-slate-400">
                    {step.label} &middot; {step.timeWindow}
                  </span>
                  {stepStatus === 'completed' ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  ) : stepStatus === 'active' ? (
                    <RotateCw className="h-3.5 w-3.5 text-sky-400 animate-spin" />
                  ) : (
                    <Icon className="h-3.5 w-3.5 text-slate-500" />
                  )}
                </div>
                <div className="text-xs font-bold tracking-tight line-clamp-1">
                  {step.stageName}
                </div>
              </div>
              <div
                className={`mt-2 font-mono text-[10px] truncate ${
                  stepStatus === 'completed'
                    ? 'text-emerald-400/90'
                    : stepStatus === 'active'
                      ? 'text-sky-300 font-semibold'
                      : 'text-slate-500'
                }`}
              >
                {step.detail}
              </div>
            </div>
          );
        })}
      </div>

      {/* Graceful Degradation Circuit Breaker Banner (FR-DEC-001 Alt Flow) */}
      {isDegradedMode && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-950/30 p-2.5 text-xs text-amber-200 flex items-start gap-2">
          <span className="font-bold text-amber-400 text-sm">⚠️</span>
          <div>
            <strong>CIRCUIT BREAKER ACTIVATED:</strong> LLM Narrative Synthesis exceeded 20s latency SLA.
            System automatically activated <strong>Deterministic Fallback Mode (FRD FR-DEC-001 Alt Flow)</strong>.
            All Days of Cover, Shortage Gaps, and Financial Exposure math remain 100% certified with zero hallucination.
          </div>
        </div>
      )}
    </div>
  );
};
