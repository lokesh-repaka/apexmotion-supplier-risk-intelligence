/**
 * HITL Approval Modal Main Component (P12-4)
 *
 * Implements the modal dialog for human-in-the-loop cryptographic spend sign-offs:
 * - Displays action summary, spend tier badge, and dual-approval progress tracker
 * - Hosts ECDSA token submission form
 * - Emits audit events and reflects state changes in the approval queue
 */

import React from 'react';
import {
  DollarSign,
  FileCheck,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useApprovalStore } from '../../stores/useApprovalStore';
import { DualApprovalProgress } from './DualApprovalProgress';
import { ECDSATokenForm } from './ECDSATokenForm';
import { SpendTierBadge } from './SpendTierBadge';

interface HITLApprovalModalProps {
  onSuccess?: () => void;
}

export const HITLApprovalModal: React.FC<HITLApprovalModalProps> = ({ onSuccess }) => {
  const {
    isModalOpen,
    currentApproval,
    activeScenario,
    isSigning,
    isRejecting,
    error,
    closeModal,
    submitSignature,
    rejectApproval,
  } = useApprovalStore();

  if (!isModalOpen || !currentApproval) return null;

  const numericAmount = Number(currentApproval.amount_usd);
  const actionTitle =
    activeScenario?.title || `Authorize ${currentApproval.action_type.replace('_', ' ')}`;

  const handleSubmitSignature = async (token: string, notes?: string) => {
    await submitSignature(currentApproval.id, token, notes);
    if (onSuccess) {
      onSuccess();
    }
  };

  const handleReject = async (reason: string) => {
    await rejectApproval(currentApproval.id, reason);
    if (onSuccess) {
      onSuccess();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-2xl rounded-2xl border border-slate-700 bg-[#0c111d] p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
        {/* Modal Top Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm sm:text-base font-bold text-white tracking-tight">
                  {actionTitle}
                </h3>
                <span className="font-mono text-[10px] text-slate-400 font-bold bg-slate-800 px-1.5 py-0.5 rounded">
                  {currentApproval.id}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Human-in-the-Loop Cryptographic Spend Authorization (AWS KMS ECDSA P-256)
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={closeModal}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Action Summary Card */}
        <div className="rounded-xl bg-[#060911] border border-slate-800 p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block">
              Committed Expenditure Amount:
            </span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <DollarSign className="h-4 w-4 text-emerald-400 self-center" />
              <span className="text-xl sm:text-2xl font-black font-mono text-white">
                {numericAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className="text-xs text-slate-400 font-mono">USD</span>
            </div>
          </div>

          <div className="text-right">
            <span className="text-[10px] uppercase font-bold text-slate-500 block">
              Impacted Alert:
            </span>
            <span className="font-mono text-xs font-semibold text-sky-400">
              {currentApproval.alert_id || 'ALT-NC-001'}
            </span>
            <span className="text-[10px] text-slate-400 block mt-0.5">
              NanoCore Semiconductor Cleanroom Fire
            </span>
          </div>
        </div>

        {/* 1. Spend Tier Router Meter & Governance Rules */}
        <SpendTierBadge
          amountUsd={currentApproval.amount_usd}
          spendTier={currentApproval.spend_tier}
        />

        {/* 2. Dual Approval Progress Tracker (Shown for DUAL_VP or multiple signers) */}
        <DualApprovalProgress
          approvedBy={currentApproval.approved_by}
          status={currentApproval.status}
          spendTier={currentApproval.spend_tier}
          expiresAt={currentApproval.expires_at}
        />

        {/* 3. ECDSA Token Submission Form */}
        <ECDSATokenForm
          approvalId={currentApproval.id}
          actionType={currentApproval.action_type}
          amountUsd={currentApproval.amount_usd}
          spendTier={currentApproval.spend_tier}
          status={currentApproval.status}
          approvedCount={currentApproval.approved_by.length}
          onSubmitSignature={handleSubmitSignature}
          onReject={handleReject}
          isSubmitting={isSigning || isRejecting}
          error={error}
        />

        {/* Modal Footer Controls */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-800 text-[11px] text-slate-500">
          <div className="flex items-center gap-1.5 font-mono">
            <FileCheck className="h-3.5 w-3.5 text-slate-400" />
            <span>WORM Audit Ledger Auto-Sync</span>
          </div>
          <button
            type="button"
            onClick={closeModal}
            className="rounded-lg bg-slate-800 hover:bg-slate-700 px-3.5 py-1.5 text-xs font-semibold text-slate-300 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
