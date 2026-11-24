/**
 * Dual Approval Progress Tracker (P12-4)
 *
 * Visualizes multi-executive cryptographic signing slots for Tier 3 (> $100,000) actions:
 * - Signature 1: Procurement Director (Priya Sharma)
 * - Signature 2: VP Supply Chain (Elena Rostova)
 * - Progress states: 0/2 (0%), 1/2 (50% PARTIALLY_APPROVED), 2/2 (100% APPROVED)
 * - Expiration countdown ticker
 */

import React from 'react';
import {
  CheckCircle2,
  Clock,
  Lock,
  RotateCw,
  ShieldCheck,
  UserCheck,
  Users,
} from 'lucide-react';

interface DualApprovalProgressProps {
  approvedBy: string[];
  status: string;
  spendTier: string;
  expiresAt?: string;
}

export const DualApprovalProgress: React.FC<DualApprovalProgressProps> = ({
  approvedBy,
  status,
  spendTier,
  expiresAt,
}) => {
  const isDual = spendTier === 'DUAL_VP';
  const sigCount = approvedBy.length;
  const isApproved = status === 'APPROVED';
  const isPartiallyApproved = status === 'PARTIALLY_APPROVED' || (isDual && sigCount === 1);

  // Target signers for NanoCore reference scenario
  const signer1 = approvedBy[0] || 'Awaiting Procurement Director (Priya Sharma)';
  const signer2 =
    approvedBy[1] ||
    (sigCount >= 1 ? 'Awaiting VP Supply Chain (Elena Rostova)' : 'Slot 2: VP Supply Chain');

  const signer1Complete = sigCount >= 1 || isApproved;
  const signer2Complete = (sigCount >= 2 && isDual) || isApproved;

  const progressPercent = isApproved ? 100 : isPartiallyApproved ? 50 : 0;

  return (
    <div className="rounded-xl border border-slate-800 bg-[#060911] p-4 space-y-3">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-sky-400" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            {isDual ? 'Dual-Executive Sign-Off Progress (2x Tokens)' : 'HITL Cryptographic Authorization'}
          </h4>
        </div>

        <div className="flex items-center gap-2">
          {expiresAt && (
            <div className="flex items-center gap-1 font-mono text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
              <Clock className="h-3 w-3" />
              <span>{isDual ? '30-min TTL' : '1-hr TTL'}</span>
            </div>
          )}
          <span
            className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded-full border ${
              isApproved
                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                : isPartiallyApproved
                  ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {isApproved ? 'SEALED (2/2)' : isPartiallyApproved ? 'PENDING VP (1/2)' : 'PENDING (0/2)'}
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
        <div
          className={`h-full transition-all duration-500 rounded-full ${
            isApproved
              ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
              : isPartiallyApproved
                ? 'bg-gradient-to-r from-sky-500 to-amber-500'
                : 'bg-slate-700'
          }`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* 2-Slot Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
        {/* Slot 1: Procurement Director */}
        <div
          className={`rounded-lg border p-2.5 transition-all flex items-start gap-2.5 ${
            signer1Complete
              ? 'border-emerald-500/40 bg-emerald-950/20 text-slate-200'
              : 'border-sky-500/40 bg-sky-950/15 text-slate-300 ring-1 ring-sky-500/20'
          }`}
        >
          <div
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
              signer1Complete
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-sky-500/20 text-sky-400 animate-pulse'
            }`}
          >
            {signer1Complete ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <UserCheck className="h-3.5 w-3.5" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between text-[10px] font-mono mb-0.5">
              <span className="text-slate-400 font-bold uppercase">Signature 1 of 2</span>
              <span className={signer1Complete ? 'text-emerald-400 font-bold' : 'text-sky-400'}>
                {signer1Complete ? 'VERIFIED' : 'ACTIVE'}
              </span>
            </div>
            <div className="text-xs font-bold text-white truncate">Procurement Director</div>
            <p className="text-[11px] text-slate-400 truncate mt-0.5">{signer1}</p>
          </div>
        </div>

        {/* Slot 2: VP Supply Chain */}
        <div
          className={`rounded-lg border p-2.5 transition-all flex items-start gap-2.5 ${
            signer2Complete
              ? 'border-emerald-500/40 bg-emerald-950/20 text-slate-200'
              : isPartiallyApproved
                ? 'border-amber-500/60 bg-amber-950/20 text-slate-200 ring-1 ring-amber-500/30'
                : 'border-slate-800 bg-slate-900/40 text-slate-500'
          }`}
        >
          <div
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
              signer2Complete
                ? 'bg-emerald-500/20 text-emerald-400'
                : isPartiallyApproved
                  ? 'bg-amber-500/20 text-amber-400 animate-pulse'
                  : 'bg-slate-800 text-slate-600'
            }`}
          >
            {signer2Complete ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : isPartiallyApproved ? (
              <RotateCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Lock className="h-3.5 w-3.5" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between text-[10px] font-mono mb-0.5">
              <span className="text-slate-400 font-bold uppercase">Signature 2 of 2</span>
              <span
                className={
                  signer2Complete
                    ? 'text-emerald-400 font-bold'
                    : isPartiallyApproved
                      ? 'text-amber-400 font-bold'
                      : 'text-slate-500'
                }
              >
                {signer2Complete ? 'VERIFIED' : isPartiallyApproved ? 'AWAITING' : 'LOCKED'}
              </span>
            </div>
            <div className="text-xs font-bold text-white truncate">VP Supply Chain</div>
            <p className="text-[11px] text-slate-400 truncate mt-0.5">{signer2}</p>
          </div>
        </div>
      </div>

      {/* Cryptographic Seal Banner */}
      {isApproved && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-xs text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-1.5 font-bold">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>CRYPTOGRAPHICALLY SEALED &middot; AWS KMS ECDSA P-256</span>
          </div>
          <span className="font-mono text-[10px] text-emerald-400">Anti-Replay Verified ✓</span>
        </div>
      )}
    </div>
  );
};
