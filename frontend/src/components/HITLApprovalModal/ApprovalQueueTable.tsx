/**
 * Approval Queue Table Component (P12-4)
 *
 * Renders the persistent HITL spend authorization queue:
 * - Lists pending, partially approved, and sealed approvals
 * - Spend tier badges and monetary formatting
 * - Row click opens HITLApprovalModal
 */

import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Filter,
  Lock,
  RotateCw,
  ShieldCheck,
  UserCheck,
  Users,
} from 'lucide-react';
import { useApprovalStore } from '../../stores/useApprovalStore';

export const ApprovalQueueTable: React.FC = () => {
  const {
    approvals,
    selectedApprovalId,
    isLoading,
    openModalForApproval,
    fetchApprovals,
  } = useApprovalStore();

  const [statusFilter, setStatusFilter] = useState<'ALL' | 'PENDING' | 'PARTIALLY_APPROVED' | 'APPROVED'>('ALL');

  const filteredItems = approvals.filter((item) => {
    if (statusFilter === 'ALL') return true;
    return item.status === statusFilter;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="h-2.5 w-2.5" /> APPROVED
          </span>
        );
      case 'PARTIALLY_APPROVED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400 border border-amber-500/30">
            <RotateCw className="h-2.5 w-2.5 animate-spin" /> PARTIALLY APPROVED
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold text-rose-400 border border-rose-500/30">
            REJECTED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-400 border border-sky-500/30">
            <Clock className="h-2.5 w-2.5" /> PENDING
          </span>
        );
    }
  };

  const getTierIcon = (tier: string) => {
    if (tier === 'DUAL_VP') return <Users className="h-3 w-3 text-rose-400" />;
    if (tier === 'PROC_DIRECTOR') return <Lock className="h-3 w-3 text-amber-400" />;
    return <ShieldCheck className="h-3 w-3 text-sky-400" />;
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0c111d] p-5 shadow-lg space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <UserCheck className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              HITL Spend Authorization Queue (BR-RULE-004)
            </h3>
            <p className="text-[11px] text-slate-400">
              Cryptographically Gated Actions Awaiting Category Mgr, Director, or Dual VP Sign-Off
            </p>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 text-xs">
          <Filter className="h-3.5 w-3.5 text-slate-500 mr-1" />
          {(['ALL', 'PENDING', 'PARTIALLY_APPROVED', 'APPROVED'] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-colors ${
                statusFilter === st
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
              }`}
            >
              {st.replace('_', ' ')}
            </button>
          ))}
          <button
            type="button"
            onClick={() => fetchApprovals()}
            disabled={isLoading}
            className="ml-2 p-1 text-slate-400 hover:text-white rounded"
            title="Refresh queue"
          >
            <RotateCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-900/60 text-[10px] uppercase font-bold text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2.5 px-3">Action Type</th>
              <th className="py-2.5 px-3">Spend Amount</th>
              <th className="py-2.5 px-3">Governance Tier</th>
              <th className="py-2.5 px-3">Signatures Collected</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-200">
            {filteredItems.map((item) => {
              const isSelected = item.id === selectedApprovalId;
              const numericAmount = Number(item.amount_usd);

              return (
                <tr
                  key={item.id}
                  className={`hover:bg-slate-800/40 transition-colors ${
                    isSelected ? 'bg-sky-950/20' : ''
                  }`}
                >
                  <td className="py-3 px-3">
                    <div className="font-bold text-white">{item.action_type.replace('_', ' ')}</div>
                    <span className="font-mono text-[10px] text-slate-500">{item.id}</span>
                  </td>
                  <td className="py-3 px-3 font-mono font-bold text-white">
                    ${numericAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-3">
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-300">
                      {getTierIcon(item.spend_tier)}
                      <span>{item.spend_tier}</span>
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <span className="font-mono text-xs">
                      {item.approved_by.length} / {item.spend_tier === 'DUAL_VP' ? 2 : 1}
                    </span>
                  </td>
                  <td className="py-3 px-3">{getStatusBadge(item.status)}</td>
                  <td className="py-3 px-3 text-right">
                    <button
                      type="button"
                      onClick={() => openModalForApproval(item)}
                      className="rounded-lg bg-sky-600 hover:bg-sky-500 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-colors"
                    >
                      {item.status === 'APPROVED' ? 'Inspect Seal' : 'Authorize →'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
