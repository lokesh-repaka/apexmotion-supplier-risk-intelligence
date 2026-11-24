/**
 * Role Guarded Action Component (P12-6)
 *
 * Enforces:
 * - Role-Aware Governance (CLAUDE.md Sec 10 & TASKS.md P12-6):
 *   - Strictly hides or disables spend authorization triggers for the 'analyst' role.
 *   - Displays informative role-gating alerts when an analyst views pending approvals.
 *   - Unlocks interactive authorization triggers when switched to Category Manager,
 *     Procurement Director, or VP Supply Chain personas.
 */

import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Lock,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import { useAuditStore } from '../../stores/useAuditStore';

export interface RoleGuardedActionProps {
  actionLabel?: string;
  spendAmountUsd?: number;
  spendTier?: 'CATEGORY_MGR' | 'PROC_DIRECTOR' | 'DUAL_VP';
  onTriggerApproval?: () => void;
  className?: string;
}

export const RoleGuardedAction: React.FC<RoleGuardedActionProps> = ({
  actionLabel = 'Authorize & Sign Spend Commitment',
  spendAmountUsd = 180000,
  spendTier = 'DUAL_VP',
  onTriggerApproval,
  className = '',
}) => {
  const { currentPersona } = useAuditStore();

  const isAnalyst = currentPersona.role === 'analyst';
  const canApprove = currentPersona.canApproveSpend;

  // Check if spend amount exceeds current persona's limit
  const isOverLimit =
    currentPersona.maxSpendLimitUsd !== null &&
    spendAmountUsd > currentPersona.maxSpendLimitUsd;

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${
      isAnalyst
        ? 'bg-slate-900/80 border-slate-700/80'
        : isOverLimit
        ? 'bg-amber-950/40 border-amber-600/50'
        : 'bg-[#080d1a] border-sky-800/60 shadow-lg'
    } ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white">
              HITL Capital Commitment Governance
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase bg-slate-800 text-slate-300">
              Tier: {spendTier} (${spendAmountUsd.toLocaleString()})
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Cryptographically governed spend authorization under Rule BR-RULE-004.
          </p>
        </div>

        {/* Status Indicator */}
        {isAnalyst ? (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-rose-400 bg-rose-950/60 border border-rose-600/50 px-2.5 py-1 rounded-lg">
            <Lock className="w-3.5 h-3.5" />
            <span>Analyst View-Only</span>
          </span>
        ) : isOverLimit ? (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-400 bg-amber-950/60 border border-amber-600/50 px-2.5 py-1 rounded-lg">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Exceeds Role Authority</span>
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-600/50 px-2.5 py-1 rounded-lg">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Authorized Signer</span>
          </span>
        )}
      </div>

      {/* Role Notice Banner */}
      {isAnalyst ? (
        <div className="bg-rose-950/30 border border-rose-600/40 rounded-lg p-3 text-xs text-rose-200 flex items-start gap-2.5">
          <Lock className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold text-rose-300">
              Spend Authorization Gated (Role: {currentPersona.name} &bull; Analyst)
            </div>
            <p className="text-rose-200/90 leading-relaxed text-[11px]">
              Spend sign-off is hidden for risk analysts. Committing capital (${spendAmountUsd.toLocaleString()}) requires Category Manager (up to $25k), Procurement Director (up to $100k), or VP Supply Chain (&gt; $100k) authority. Switch persona in the bar above to test authorized signing.
            </p>
          </div>
        </div>
      ) : isOverLimit ? (
        <div className="bg-amber-950/30 border border-amber-600/40 rounded-lg p-3 text-xs text-amber-200 flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold text-amber-300">
              Authority Limit Exceeded (Limit: ${currentPersona.maxSpendLimitUsd?.toLocaleString()})
            </div>
            <p className="text-amber-200/90 leading-relaxed text-[11px]">
              Action requires Dual Executive Sign-off (&gt; $100k). Switch to VP Supply Chain or Procurement Director persona to sign.
            </p>
          </div>
        </div>
      ) : null}

      {/* Action Button: Strictly rendered only if canApprove and not isAnalyst and not overLimit */}
      {!isAnalyst && canApprove && !isOverLimit && (
        <div className="pt-2 flex justify-end">
          <button
            type="button"
            onClick={onTriggerApproval}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-sky-950/50"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{actionLabel}</span>
          </button>
        </div>
      )}
    </div>
  );
};
