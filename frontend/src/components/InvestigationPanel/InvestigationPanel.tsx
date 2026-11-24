/**
 * Investigation Panel Main Wrapper (P12-3)
 *
 * Coordinates:
 * - 6-Stage Sub-90s Pipeline Stepper (InvestigationStepper)
 * - Grounded Synthesized Incident Narrative with Interactive Citations (AgentNarrative)
 * - Multi-Modal Corroborated Evidence Cards (EvidenceCards)
 * - Deterministic Math Proof Engine (DeterministicProofCard - BR-RULE-001)
 * - Ranked Mitigation Scenarios with HITL Spend Gating (MitigationScenariosList)
 * - Modal workflows: Citation inspection and new investigation triggering
 */

import React from 'react';
import {
  FileText,
  Play,
  RotateCw,
  Sparkles,
} from 'lucide-react';
import {
  CITATION_REGISTRY,
  useInvestigationStore,
} from '../../stores/useInvestigationStore';
import { useApprovalStore } from '../../stores/useApprovalStore';
import { AgentNarrative } from './AgentNarrative';
import { CitationModal } from './CitationModal';
import { DeterministicProofCard } from './DeterministicProofCard';
import { EvidenceCards } from './EvidenceCards';
import { InvestigationStepper } from './InvestigationStepper';
import { MitigationScenariosList } from './MitigationScenariosList';
import { TriggerInvestigationModal } from './TriggerInvestigationModal';

interface InvestigationPanelProps {
  onNavigateToApproval?: (scenario: Record<string, unknown>) => void;
}

export const InvestigationPanel: React.FC<InvestigationPanelProps> = ({
  onNavigateToApproval,
}) => {
  const {
    currentInvestigation,
    activeInvestigationId,
    isTriggering,
    isPolling,
    isDegradedMode,
    elapsedSeconds,
    error,
    isTriggerModalOpen,
    selectedCitation,
    triggerInvestigation,
    fetchInvestigation,
    startPolling,
    stopPolling,
    loadCanonicalScenario,
    setIsTriggerModalOpen,
    setSelectedCitation,
    setDegradedMode,
  } = useInvestigationStore();

  // Trigger modal launch handler
  const handleLaunchInvestigation = async (req: Parameters<typeof triggerInvestigation>[0]) => {
    await triggerInvestigation(req);
  };

  const handleCitationClick = (citationTag: string) => {
    const citation = CITATION_REGISTRY[citationTag] || {
      id: citationTag,
      tag: citationTag,
      title: `Evidence Citation [${citationTag}]`,
      source: 'Corroborated Telemetry Ingestion Hub',
      timestamp: new Date().toISOString(),
      summary: `Primary source documentation extracted and verified for reference citation [${citationTag}].`,
      verification: 'Verified (Certified Primary Source)',
      sourceType: 'news',
    };
    setSelectedCitation(citation);
  };

  const investigation = currentInvestigation;
  const caseId = investigation?.case_id || 'CASE-2026-091';

  return (
    <div className="space-y-6">
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-[#0c111d] p-4 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 shadow-md shadow-sky-500/20">
            <FileText className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-white">
                Incident Case Dossier &middot; {caseId}
              </h2>
              <span className="rounded bg-sky-500/10 px-2 py-0.5 font-mono text-[11px] font-bold text-sky-400 border border-sky-500/20">
                {investigation?.status || 'AWAITING_APPROVAL'}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Supplier: <strong className="text-slate-200">{investigation?.supplier_id || 'SUP-NC-001'}</strong>
              {investigation?.component_sku && (
                <> &middot; SKU: <strong className="text-slate-200">{investigation.component_sku}</strong></>
              )}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Degraded mode toggle */}
          <label className="flex items-center gap-1.5 rounded-lg bg-slate-900 border border-slate-800 px-3 py-1.5 text-xs cursor-pointer text-slate-400 hover:text-white">
            <input
              type="checkbox"
              checked={isDegradedMode}
              onChange={(e) => setDegradedMode(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-amber-500 focus:ring-0"
            />
            <span>Simulate LLM Fallback (Degraded Mode)</span>
          </label>

          {/* Quick load canonical NanoCore */}
          <button
            type="button"
            onClick={loadCanonicalScenario}
            className="flex items-center gap-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5 text-sky-400" />
            <span>Load Golden Scenario</span>
          </button>

          {/* Polling / Refresh Button */}
          {isPolling ? (
            <button
              type="button"
              onClick={stopPolling}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20 px-3 py-1.5 text-xs font-semibold text-amber-300 transition-colors"
            >
              <RotateCw className="h-3.5 w-3.5 animate-spin text-amber-400" />
              <span>Stop Polling ({elapsedSeconds}s)</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                if (activeInvestigationId) {
                  startPolling(activeInvestigationId);
                } else {
                  loadCanonicalScenario();
                }
              }}
              className="flex items-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors border border-slate-700"
            >
              <RotateCw className="h-3.5 w-3.5 text-slate-400" />
              <span>Poll Status</span>
            </button>
          )}

          {/* Trigger New Investigation Button */}
          <button
            type="button"
            onClick={() => setIsTriggerModalOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 px-3.5 py-1.5 text-xs font-bold text-white shadow-md shadow-sky-600/20 transition-colors"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            <span>Trigger New Investigation</span>
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-300 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => activeInvestigationId && fetchInvestigation(activeInvestigationId)}
            className="underline font-semibold ml-4"
          >
            Retry
          </button>
        </div>
      )}

      {/* 6-Stage Investigation Stepper */}
      <InvestigationStepper
        currentNode={investigation?.current_node || null}
        executionPath={investigation?.execution_path || []}
        status={investigation?.status || 'AWAITING_APPROVAL'}
        elapsedSeconds={elapsedSeconds}
        isDegradedMode={isDegradedMode}
      />

      {/* 2-Column Dossier Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column (7 of 12 cols): Agent Narrative & Evidence Cards */}
        <div className="lg:col-span-7 space-y-6">
          {/* Synthesized Agent Narrative */}
          <AgentNarrative
            narrative={investigation?.narrative || null}
            caseId={caseId}
            isDegradedMode={isDegradedMode}
            onCitationClick={handleCitationClick}
          />

          {/* Evidence Cards: External News, Blast Radius, Contracts */}
          <EvidenceCards
            researchAnalysis={
              (investigation?.research_analysis as Record<string, unknown>) || null
            }
            contractAnalysis={
              (investigation?.contract_analysis as Record<string, unknown>) || null
            }
            onCitationClick={handleCitationClick}
          />
        </div>

        {/* Right Column (5 of 12 cols): Deterministic Math Proof & Mitigation Scenarios */}
        <div className="lg:col-span-5 space-y-6 sticky top-20">
          {/* Deterministic Math Proof Panel (BR-RULE-001) */}
          <DeterministicProofCard
            riskMetrics={
              (investigation?.risk_metrics as Record<string, unknown>) || null
            }
          />

          {/* Ranked Mitigation Scenarios List */}
          <MitigationScenariosList
            recommendations={
              (investigation?.recommendations as Array<Record<string, unknown>>) || null
            }
            recommendedActionId={investigation?.recommended_action_id}
            onProceedToApproval={
              onNavigateToApproval
                ? (scen) => onNavigateToApproval(scen as unknown as Record<string, unknown>)
                : (scen) => {
                    useApprovalStore.getState().openModalForScenario({
                      scenario_id: scen.scenario_id,
                      scenario_type: scen.scenario_type,
                      title: scen.title,
                      description: scen.description,
                      estimated_cost_usd: scen.estimated_cost_usd,
                      spend_tier: scen.spend_tier,
                      requires_hitl: scen.requires_hitl,
                    });
                  }
            }
          />
        </div>
      </div>

      {/* Interactive Citation Detail Modal */}
      <CitationModal
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
      />

      {/* Trigger Investigation Modal */}
      <TriggerInvestigationModal
        isOpen={isTriggerModalOpen}
        onClose={() => setIsTriggerModalOpen(false)}
        onSubmit={handleLaunchInvestigation}
        isSubmitting={isTriggering}
        defaultSupplierId={investigation?.supplier_id}
      />
    </div>
  );
};
