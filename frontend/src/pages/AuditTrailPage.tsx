/**
 * Forensic Audit Trail Page (P12-6)
 *
 * Implements:
 * - Tamper-Evident WORM Audit Ledger view (Amazon S3 Object Lock, 7-year retention).
 * - Chronological immutable timeline per alert (Genesis to PO dispatch).
 * - Role-Aware Governance (Strictly hides/disables spend approval for analyst role).
 * - Interactive Persona / Keycloak Role Switcher.
 * - Continuous CI/CD automated regression evaluation gate (FRD FR-GOV-002).
 */

import React, { useEffect } from 'react';
import {
  ArrowLeft,
  Sparkles,
} from 'lucide-react';
import {
  AuditDetailCard,
  AuditTimeline,
  EvalsGateCard,
  MerkleIntegrityBanner,
  PersonaRoleBar,
  RoleGuardedAction,
} from '../components/AuditTrail';
import { useAuditStore } from '../stores/useAuditStore';
import { useApprovalStore } from '../stores/useApprovalStore';

export interface AuditTrailPageProps {
  onBackToDashboard?: () => void;
  onNavigateToInvestigation?: () => void;
  onNavigateToApprovals?: () => void;
}

export const AuditTrailPage: React.FC<AuditTrailPageProps> = ({
  onBackToDashboard,
  onNavigateToInvestigation,
  onNavigateToApprovals,
}) => {
  const {
    blocks,
    loadCanonicalAuditTrail,
  } = useAuditStore();

  const { approvals, openModalForApproval } = useApprovalStore();

  useEffect(() => {
    if (blocks.length === 0) {
      loadCanonicalAuditTrail();
    }
  }, [blocks, loadCanonicalAuditTrail]);

  const handleTriggerSpendApproval = () => {
    // Open the HITL Modal with Option 1 ($180,000 Air Charter)
    const item = approvals.find((a) => a.id === 'appr-nc-001') || approvals[0];
    if (item) {
      openModalForApproval(item);
    }
    onNavigateToApprovals?.();
  };

  return (
    <div className="p-6 max-w-[1720px] w-full mx-auto space-y-5">
      {/* Navigation Breadcrumb Bar */}
      {(onBackToDashboard || onNavigateToInvestigation) && (
        <div className="flex items-center justify-between text-xs text-slate-400 bg-[#080d1a] border border-slate-800 rounded-xl px-4 py-2">
          <div className="flex items-center gap-3">
            {onBackToDashboard && (
              <button
                type="button"
                onClick={onBackToDashboard}
                className="text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Operational Dashboard</span>
              </button>
            )}
            <span>/</span>
            <span className="text-slate-200 font-medium">Forensic WORM Ledger</span>
          </div>

          {onNavigateToInvestigation && (
            <button
              type="button"
              onClick={onNavigateToInvestigation}
              className="text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Investigation Case Dossier</span>
            </button>
          )}
        </div>
      )}

      {/* 1. Persona & Role-Aware Switcher Bar */}
      <PersonaRoleBar />

      {/* 2. WORM Compliance & Merkle Hash Integrity Banner */}
      <MerkleIntegrityBanner />

      {/* 3. Role-Guarded Action Trigger (Hides approve for analyst) */}
      <RoleGuardedAction
        actionLabel="Execute Cryptographic Sign-Off (Option 1: $180,000 Air Charter)"
        spendAmountUsd={180000}
        spendTier="DUAL_VP"
        onTriggerApproval={handleTriggerSpendApproval}
      />

      {/* 4. Main Timeline & Detail Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Chronological Audit Timeline */}
        <div className="lg:col-span-7 w-full">
          <AuditTimeline />
        </div>

        {/* Right Column: Deep Forensic Block Inspection */}
        <div className="lg:col-span-5 w-full">
          <AuditDetailCard />
        </div>
      </div>

      {/* 5. Continuous CI/CD Evals Gate & 7 Platform Rules */}
      <EvalsGateCard />
    </div>
  );
};

