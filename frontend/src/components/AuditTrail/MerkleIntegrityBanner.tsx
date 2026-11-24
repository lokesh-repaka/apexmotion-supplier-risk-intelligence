/**
 * Merkle Integrity Banner Component (P12-6)
 *
 * Displays:
 * - WORM Audit Ledger compliance status (S3 Object Lock Compliance Mode, 7-year retention).
 * - Live cryptographic verification badge (&check; Zero Tamper Events).
 * - Interactive 'Verify Merkle Chain' trigger validating SHA-256 block hashes from Genesis.
 * - Active alert filter selector.
 */

import React from 'react';
import {
  CheckCircle2,
  ChevronDown,
  Database,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { useAuditStore } from '../../stores/useAuditStore';

export interface MerkleIntegrityBannerProps {
  onAlertChange?: (alertId: string) => void;
}

const PRESET_ALERTS = [
  { id: 'ALT-NC-001', label: 'ALT-NC-001 · NanoCore Fab 2 Cleanroom Fire (Critical)' },
  { id: 'ALT-BE-002', label: 'ALT-BE-002 · BetaElectro Nuremberg Logistics Bottleneck' },
  { id: 'ALT-MC-003', label: 'ALT-MC-003 · MicroChip Global AML Qualification' },
];

export const MerkleIntegrityBanner: React.FC<MerkleIntegrityBannerProps> = ({
  onAlertChange,
}) => {
  const {
    selectedAlertId,
    setSelectedAlertId,
    fetchAlertAuditTrail,
    isVerifying,
    isIntegrityVerified,
    tamperCount,
    verifyMerkleIntegrity,
    blocks,
  } = useAuditStore();

  const handleSelectAlert = (id: string) => {
    setSelectedAlertId(id);
    fetchAlertAuditTrail(id);
    onAlertChange?.(id);
  };

  return (
    <div className="bg-[#0b1120] border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Title and WORM Standard description */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-sky-400 bg-sky-950/80 border border-sky-600/50 px-2 py-0.5 rounded">
              <Database className="w-3 h-3 text-sky-400" />
              WORM S3 Compliance Mode
            </span>
            <span className="text-slate-600 text-xs">&bull;</span>
            <span className="text-slate-400 text-xs font-mono">
              7-Year Mandatory Retention &bull; ISO/TS 16949
            </span>
          </div>

          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            Tamper-Evident WORM Audit Ledger & Merkle Timeline
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Cryptographically sealed append-only ledger. Every state transition, AI agent decision, and HITL authorization is SHA-256 chained to Genesis.
          </p>
        </div>

        {/* Verification Status & Trigger */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Integrity Badge */}
          <div
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold border transition-all ${
              isIntegrityVerified
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60 shadow-[0_0_12px_rgba(16,185,129,0.25)]'
                : 'bg-rose-950/80 text-rose-300 border-rose-600/60 shadow-[0_0_12px_rgba(244,63,94,0.3)]'
            }`}
          >
            {isIntegrityVerified ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Zero Tamper Events ({blocks.length}/{blocks.length} Blocks Sealed)</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4 text-rose-400" />
                <span>{tamperCount} Tamper Violations Detected</span>
              </>
            )}
          </div>

          {/* Recalculate / Verify Button */}
          <button
            type="button"
            onClick={verifyMerkleIntegrity}
            disabled={isVerifying}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold border border-slate-700 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isVerifying ? 'animate-spin text-sky-400' : ''}`} />
            <span>{isVerifying ? 'Verifying Hashes...' : 'Verify Merkle Chain'}</span>
          </button>
        </div>
      </div>

      {/* Alert Selector Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800/80 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-slate-400 font-medium">Active Alert Context:</span>
          <div className="relative">
            <select
              value={selectedAlertId}
              onChange={(e) => handleSelectAlert(e.target.value)}
              className="appearance-none bg-[#080d1a] border border-slate-700 rounded-xl pl-3 pr-8 py-1.5 text-xs text-slate-200 font-medium focus:outline-none focus:border-sky-500 cursor-pointer shadow-sm"
            >
              {PRESET_ALERTS.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
          <span>Chain Length: <strong className="text-white">{blocks.length} Blocks</strong></span>
          <span>&bull;</span>
          <span>Hash Algorithm: <strong className="text-sky-400">SHA-256</strong></span>
          <span>&bull;</span>
          <span>Key Authorization: <strong className="text-emerald-400">AWS KMS ECDSA P-256</strong></span>
        </div>
      </div>
    </div>
  );
};
