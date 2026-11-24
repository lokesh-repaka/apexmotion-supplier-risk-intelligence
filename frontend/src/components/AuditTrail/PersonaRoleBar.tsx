/**
 * Persona & Role-Aware Governance Switcher (P12-6)
 *
 * Implements:
 * - Interactive persona switcher across Keycloak roles:
 *   - Risk Analyst: Strictly read-only (spend approve button hidden).
 *   - Category Manager: Tier 1 authorization (<= $25,000).
 *   - Procurement Director: Tier 2 authorization (<= $100,000) & Dual Signer 1.
 *   - VP Supply Chain: Tier 3 dual authorization (> $100,000).
 *   - Compliance Auditor: Forensic audit & WORM inspection.
 * - Live permission indicators and spend limits.
 */

import React from 'react';
import {
  Lock,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import {
  USER_PERSONAS,
  type UserRoleType,
  useAuditStore,
} from '../../stores/useAuditStore';

export const PersonaRoleBar: React.FC = () => {
  const { currentPersona, setCurrentPersona } = useAuditStore();

  return (
    <div className="bg-[#080d1a] border border-slate-800 rounded-2xl p-4 shadow-lg space-y-3">
      {/* Top Header: Active Persona Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-3">
          {/* Avatar Icon */}
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm shadow-md ${
              currentPersona.role === 'analyst'
                ? 'bg-slate-800 text-slate-300 ring-2 ring-slate-600'
                : currentPersona.role === 'category_manager'
                ? 'bg-sky-950 text-sky-300 ring-2 ring-sky-500'
                : currentPersona.role === 'procurement_director'
                ? 'bg-indigo-950 text-indigo-300 ring-2 ring-indigo-500'
                : currentPersona.role === 'vp_supply_chain'
                ? 'bg-amber-950 text-amber-300 ring-2 ring-amber-500'
                : 'bg-emerald-950 text-emerald-300 ring-2 ring-emerald-500'
            }`}
          >
            {currentPersona.initials}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-sm">
                {currentPersona.name}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                  currentPersona.role === 'analyst'
                    ? 'bg-slate-800 text-slate-300 border border-slate-700'
                    : currentPersona.role === 'category_manager'
                    ? 'bg-sky-950 text-sky-300 border border-sky-700/50'
                    : currentPersona.role === 'procurement_director'
                    ? 'bg-indigo-950 text-indigo-300 border border-indigo-700/50'
                    : currentPersona.role === 'vp_supply_chain'
                    ? 'bg-amber-950 text-amber-300 border border-amber-700/50'
                    : 'bg-emerald-950 text-emerald-300 border border-emerald-700/50'
                }`}
              >
                {currentPersona.role.replace('_', ' ')}
              </span>

              {/* Spend Authority Status Badge */}
              {currentPersona.canApproveSpend ? (
                <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-600/50 px-2 py-0.5 rounded-full">
                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                  <span>
                    Spend Authority:{' '}
                    {currentPersona.maxSpendLimitUsd
                      ? `Up to $${currentPersona.maxSpendLimitUsd.toLocaleString()}`
                      : 'Dual VP (> $100k)'}
                  </span>
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[11px] font-semibold text-rose-400 bg-rose-950/60 border border-rose-600/50 px-2 py-0.5 rounded-full">
                  <Lock className="w-3 h-3 text-rose-400" />
                  <span>Read-Only (Spend Gated)</span>
                </span>
              )}
            </div>

            <p className="text-xs text-slate-400 mt-0.5">
              {currentPersona.title} &bull;{' '}
              <span className="text-slate-300">{currentPersona.description}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Role Switcher Pills */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <span className="text-xs text-slate-400 font-medium mr-1 flex items-center gap-1">
          <UserCheck className="w-3.5 h-3.5 text-sky-400" />
          <span>Switch Keycloak Persona:</span>
        </span>

        {(Object.keys(USER_PERSONAS) as UserRoleType[]).map((roleKey) => {
          const p = USER_PERSONAS[roleKey];
          const isSelected = currentPersona.role === roleKey;

          return (
            <button
              key={roleKey}
              type="button"
              onClick={() => setCurrentPersona(roleKey)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                isSelected
                  ? 'bg-sky-600 text-white shadow-md ring-1 ring-sky-400'
                  : 'bg-slate-900/90 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
              }`}
            >
              <span className="font-mono text-[10px] opacity-75">[{p.initials}]</span>
              <span>{p.title.split(' ')[0]} {p.title.split(' ')[1] || ''}</span>
              {roleKey === 'analyst' && (
                <span className="text-[10px] bg-slate-800 px-1 rounded text-slate-400">
                  Read-Only
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
