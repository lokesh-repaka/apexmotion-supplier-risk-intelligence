/**
 * Spend Tier Badge & Router Component (P12-4)
 *
 * Visualizes the 3-tier cryptographic spend governance hierarchy (BR-RULE-004):
 * - Tier 1: Spend <= $25,000 -> Category Manager (1x ECDSA token, 1-hr TTL)
 * - Tier 2: Spend $25,001 - $100,000 -> Procurement Director (1x ECDSA token, 1-hr TTL)
 * - Tier 3: Spend > $100,000 -> Dual Sign-Off: Director + VP Supply Chain (2x tokens, 30-min TTL)
 */

import React from 'react';
import { Lock, ShieldAlert, ShieldCheck, Users } from 'lucide-react';
import { resolveSpendTier } from '../../stores/useApprovalStore';

interface SpendTierBadgeProps {
  amountUsd: number | string;
  spendTier?: string;
}

export const SpendTierBadge: React.FC<SpendTierBadgeProps> = ({
  amountUsd,
  spendTier,
}) => {
  const numericAmount = typeof amountUsd === 'number' ? amountUsd : parseFloat(amountUsd) || 0;
  const activeTier = spendTier || resolveSpendTier(numericAmount);

  return (
    <div className="space-y-3">
      {/* 3-Node Spend Router Visualization */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        {/* Tier 1 Node */}
        <div
          className={`rounded-xl border p-3 transition-all flex items-start gap-2.5 ${
            activeTier === 'CATEGORY_MGR'
              ? 'border-sky-500/80 bg-sky-950/30 text-white shadow-md shadow-sky-500/10 ring-1 ring-sky-500/40'
              : 'border-slate-800 bg-slate-900/40 text-slate-500'
          }`}
        >
          <div
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
              activeTier === 'CATEGORY_MGR'
                ? 'bg-sky-500/20 text-sky-400'
                : 'bg-slate-800 text-slate-500'
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400">
                Tier 1 &middot; &le; $25k
              </span>
              {activeTier === 'CATEGORY_MGR' && (
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
              )}
            </div>
            <div className="text-xs font-bold tracking-tight">Category Manager</div>
            <p className="text-[10px] text-slate-400 mt-0.5">1x ECDSA Token &middot; 1h TTL</p>
          </div>
        </div>

        {/* Tier 2 Node */}
        <div
          className={`rounded-xl border p-3 transition-all flex items-start gap-2.5 ${
            activeTier === 'PROC_DIRECTOR'
              ? 'border-amber-500/80 bg-amber-950/30 text-white shadow-md shadow-amber-500/10 ring-1 ring-amber-500/40'
              : 'border-slate-800 bg-slate-900/40 text-slate-500'
          }`}
        >
          <div
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
              activeTier === 'PROC_DIRECTOR'
                ? 'bg-amber-500/20 text-amber-400'
                : 'bg-slate-800 text-slate-500'
            }`}
          >
            <Lock className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400">
                Tier 2 &middot; $25k–$100k
              </span>
              {activeTier === 'PROC_DIRECTOR' && (
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
              )}
            </div>
            <div className="text-xs font-bold tracking-tight">Procurement Director</div>
            <p className="text-[10px] text-slate-400 mt-0.5">1x ECDSA Token &middot; 1h TTL</p>
          </div>
        </div>

        {/* Tier 3 Node */}
        <div
          className={`rounded-xl border p-3 transition-all flex items-start gap-2.5 ${
            activeTier === 'DUAL_VP'
              ? 'border-rose-500/80 bg-rose-950/30 text-white shadow-md shadow-rose-500/10 ring-1 ring-rose-500/40'
              : 'border-slate-800 bg-slate-900/40 text-slate-500'
          }`}
        >
          <div
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
              activeTier === 'DUAL_VP'
                ? 'bg-rose-500/20 text-rose-400'
                : 'bg-slate-800 text-slate-500'
            }`}
          >
            <Users className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400">
                Tier 3 &middot; &gt; $100k
              </span>
              {activeTier === 'DUAL_VP' && (
                <span className="h-1.5 w-1.5 rounded-full bg-rose-400 animate-pulse" />
              )}
            </div>
            <div className="text-xs font-bold tracking-tight">Dual Executive VP</div>
            <p className="text-[10px] text-slate-400 mt-0.5">2x Distinct Tokens &middot; 30m TTL</p>
          </div>
        </div>
      </div>

      {/* Dynamic Rule Explainer */}
      <div
        className={`rounded-lg border px-3.5 py-2.5 text-xs flex items-center justify-between ${
          activeTier === 'DUAL_VP'
            ? 'border-rose-500/30 bg-rose-950/20 text-rose-300'
            : activeTier === 'PROC_DIRECTOR'
              ? 'border-amber-500/30 bg-amber-950/20 text-amber-300'
              : 'border-sky-500/30 bg-sky-950/20 text-sky-300'
        }`}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>
            {activeTier === 'DUAL_VP' && (
              <>
                <strong>Dual-Executive Sign-Off Enforced:</strong> Total spend ($
                {numericAmount.toLocaleString('en-US')}) exceeds $100,000 threshold under{' '}
                <strong className="underline">Rule BR-RULE-004</strong>. Two distinct cryptographic
                ECDSA P-256 tokens are required (Procurement Director + VP Supply Chain).
              </>
            )}
            {activeTier === 'PROC_DIRECTOR' && (
              <>
                <strong>Procurement Director Authorization Required:</strong> Total spend ($
                {numericAmount.toLocaleString('en-US')}) is within $25,001–$100,000 threshold. 1x
                ECDSA token required.
              </>
            )}
            {activeTier === 'CATEGORY_MGR' && (
              <>
                <strong>Category Manager Sign-Off:</strong> Total spend ($
                {numericAmount.toLocaleString('en-US')}) is under $25,000 threshold. 1x ECDSA token
                required.
              </>
            )}
          </span>
        </div>
      </div>
    </div>
  );
};
