/**
 * ECDSA Token Submission Form (P12-4)
 *
 * Implements cryptographic spend token authorization form:
 * - Accepts AWS KMS ECDSA P-256 signatures or JWT auth tokens
 * - Quick simulation generator for local testing and developer walkthroughs
 * - Anti-replay and confirmation reviews (BR-RULE-001 & BR-RULE-004)
 * - Clear error diagnostics for token expiry (400), replay (409), or invalid signature (401)
 */

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Key,
  RotateCw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';

interface ECDSATokenFormProps {
  approvalId: string;
  actionType: string;
  amountUsd: number | string;
  spendTier: string;
  status: string;
  approvedCount: number;
  onSubmitSignature: (token: string, notes?: string) => Promise<void>;
  onReject?: (reason: string) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}

export const ECDSATokenForm: React.FC<ECDSATokenFormProps> = ({
  actionType,
  amountUsd,
  spendTier,
  status,
  approvedCount,
  onSubmitSignature,
  onReject,
  isSubmitting,
  error,
}) => {
  const [token, setToken] = useState('');
  const [notes, setNotes] = useState(
    'Reviewed deterministic inventory runway and contract terms. Authorizing under BR-RULE-004.'
  );
  const [isReviewedConfirmed, setIsReviewedConfirmed] = useState(false);
  const [isRejectMode, setIsRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const isApproved = status === 'APPROVED';
  const isRejected = status === 'REJECTED';
  const isDual = spendTier === 'DUAL_VP';

  // Helper to generate a realistic simulated ECDSA P-256 JWT token for quick testing
  const handleSimulateToken = () => {
    const encodeStr = (str: string) => {
      try {
        return window.btoa(str);
      } catch {
        return 'eyJhY3Rpb24iOiJzaWduIn0';
      }
    };
    const header = encodeStr(JSON.stringify({ alg: 'ES256', typ: 'JWT', kid: 'kms-p256-hitl-key-01' }));
    const payload = encodeStr(
      JSON.stringify({
        sub: approvedCount === 0 ? 'priya.sharma@apexmotion.com' : 'elena.rostova@apexmotion.com',
        role: approvedCount === 0 ? 'PROCUREMENT_DIRECTOR' : 'VP_SUPPLY_CHAIN',
        action_type: actionType,
        amount_usd: String(amountUsd),
        spend_tier: spendTier,
        nonce: Math.random().toString(36).substring(2, 10),
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 1800,
      })
    );
    const mockSignature =
      'MEQCIDz81l1Q1oHh_mK0LwV2P4qS6jZ_tY3uW7x9E1vN2bXaAiBq8wE3rT5yU7iO9pA1sD3fG5hJ7kL9zX2cV4bN6mQ8';
    setToken(`${header}.${payload}.${mockSignature}`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    await onSubmitSignature(token.trim(), notes.trim() || undefined);
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) return;
    if (onReject) {
      await onReject(rejectReason.trim());
      setIsRejectMode(false);
    }
  };

  if (isApproved) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-5 text-center space-y-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 mx-auto">
          <CheckCircle2 className="h-7 w-7" />
        </div>
        <h4 className="text-sm font-bold text-white">
          Cryptographic Authorization Fully Executed
        </h4>
        <p className="text-xs text-slate-300 max-w-md mx-auto leading-relaxed">
          All required cryptographic signatures have been validated against AWS KMS ECDSA P-256
          and committed to the immutable WORM audit ledger. Dispatch signals have been emitted.
        </p>
      </div>
    );
  }

  if (isRejected) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-5 text-center space-y-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/20 text-rose-400 mx-auto">
          <AlertTriangle className="h-7 w-7" />
        </div>
        <h4 className="text-sm font-bold text-white">Action Authorization Rejected</h4>
        <p className="text-xs text-slate-300 max-w-md mx-auto leading-relaxed">
          This spend request has been officially declined and flagged in the forensic audit ledger.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Error Banner */}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-300 flex items-start gap-2">
          <ShieldAlert className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <strong className="block text-rose-200">Signature Verification Failed:</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {isRejectMode ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/15 p-4 space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-rose-300">
            Decline Spend Authorization
          </h4>
          <p className="text-xs text-slate-400">
            Provide an audit-logged justification for declining this spend authorization request:
          </p>
          <textarea
            rows={2}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="e.g. Excessive spot freight rates; prefer standard secondary supplier allocation."
            className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white focus:outline-none focus:border-rose-500"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsRejectMode(false)}
              className="px-3 py-1.5 rounded-lg bg-slate-800 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReject}
              disabled={isSubmitting || !rejectReason.trim()}
              className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white disabled:opacity-50"
            >
              Confirm Rejection &rarr;
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Token Header with Quick Simulation Button */}
          <div className="flex items-center justify-between">
            <label className="block text-xs font-medium text-slate-300">
              <span className="flex items-center gap-1.5">
                <Key className="h-3.5 w-3.5 text-sky-400" />
                <span>
                  {isDual && approvedCount === 1
                    ? 'VP Supply Chain Cryptographic Token (Signature 2)'
                    : 'Cryptographic ECDSA Token (P-256)'}
                </span>
              </span>
            </label>

            <button
              type="button"
              onClick={handleSimulateToken}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300 bg-sky-500/10 hover:bg-sky-500/20 px-2.5 py-1 rounded-md border border-sky-500/20 transition-colors"
            >
              <Sparkles className="h-3 w-3" />
              <span>Simulate Valid Token</span>
            </button>
          </div>

          {/* Token Textarea */}
          <textarea
            rows={3}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste AWS KMS ECDSA P-256 signature or signed Keycloak authorization token..."
            className="w-full rounded-lg bg-[#060911] border border-slate-800 px-3 py-2 font-mono text-[11px] text-sky-300 placeholder:text-slate-600 focus:outline-none focus:border-sky-500"
            required
          />

          {/* Signer Notes */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              Signer Executive Audit Notes (Optional)
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Confirmed with plant manager; proceed with expedite."
              className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>

          {/* Mandatory Review Confirmation Checkbox */}
          <div className="rounded-lg bg-slate-900/60 border border-slate-800 p-3 flex items-start gap-2.5">
            <input
              type="checkbox"
              id="confirmReview"
              checked={isReviewedConfirmed}
              onChange={(e) => setIsReviewedConfirmed(e.target.checked)}
              className="mt-0.5 rounded bg-slate-800 border-slate-700 text-sky-500 focus:ring-0"
              required
            />
            <label
              htmlFor="confirmReview"
              className="text-[11px] text-slate-300 leading-snug cursor-pointer select-none"
            >
              <strong>Mandatory Review Attestation:</strong> I verify that I have reviewed the certified
              deterministic calculations (Days of Cover = 7.68d, Gap = 1.32d, Exposure = $2,448,105)
              and approve this capital commitment under <strong>Governance Rules BR-RULE-001 &amp; BR-RULE-004</strong>.
            </label>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            {onReject && (
              <button
                type="button"
                onClick={() => setIsRejectMode(true)}
                className="text-xs text-rose-400 hover:text-rose-300 font-semibold"
              >
                Reject Action &rarr;
              </button>
            )}

            <div className="flex items-center gap-2 ml-auto">
              <button
                type="submit"
                disabled={isSubmitting || !token.trim() || !isReviewedConfirmed}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-emerald-600/20 transition-colors disabled:opacity-40"
              >
                {isSubmitting ? (
                  <>
                    <RotateCw className="h-3.5 w-3.5 animate-spin" />
                    <span>Validating KMS Token...</span>
                  </>
                ) : (
                  <>
                    <Key className="h-3.5 w-3.5" />
                    <span>
                      {isDual && approvedCount === 1
                        ? 'Sign as VP Supply Chain &rarr;'
                        : isDual
                          ? 'Sign as Procurement Director &rarr;'
                          : 'Sign & Dispatch Authorized Action &rarr;'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
};
