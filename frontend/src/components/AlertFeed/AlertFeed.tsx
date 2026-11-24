/**
 * Kafka-Driven Live Alert Feed Component (P12-2)
 *
 * Implements real-time disruption alert streaming pushed over WebSocket:
 * - Reactive MSK Kafka stream status badge with health pulse.
 * - Live alert cards with exact Decimal exposure and days of cover.
 * - HITL spend authority gates badge (DUAL_VP, PROC_DIRECTOR, CATEGORY_MGR).
 * - Inline acknowledgment trigger with optimistic state transition.
 */

import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  Lock,
  Radio,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import type { RiskAlert, WebSocketAlertData } from '../../api/types';

interface AlertFeedProps {
  alerts: RiskAlert[];
  liveAlerts: WebSocketAlertData[];
  isConnected: boolean;
  isConnecting: boolean;
  wsError: string | null;
  selectedAlertId: string | null;
  onSelectAlert: (id: string | null) => void;
  onAcknowledgeAlert: (alertId: string, notes?: string) => Promise<void>;
  onClearLiveAlerts: () => void;
}

export const AlertFeed: React.FC<AlertFeedProps> = ({
  alerts,
  liveAlerts,
  isConnected,
  isConnecting,
  wsError,
  selectedAlertId,
  onSelectAlert,
  onAcknowledgeAlert,
  onClearLiveAlerts,
}) => {
  const [feedFilter, setFeedFilter] = useState<'ALL' | 'CRITICAL' | 'HITL'>('ALL');
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  // Combine live WebSocket alerts and persisted alerts, prioritizing live alerts
  const unifiedAlerts = useMemo(() => {
    const map = new Map<string, {
      id: string;
      supplier_id?: string | null;
      component_sku: string;
      risk_level: string;
      days_of_cover?: string | number | null;
      gap_days?: string | number | null;
      shortage_volume?: number | null;
      financial_exposure?: string | number | null;
      status: string;
      hitl_required?: boolean;
      hitl_tier?: string | null;
      timestamp: string;
      isLive: boolean;
    }>();

    // 1. Persisted alerts
    for (const a of alerts) {
      map.set(a.id, {
        id: a.id,
        supplier_id: a.supplier_id,
        component_sku: a.component_sku,
        risk_level: a.risk_level,
        days_of_cover: a.days_of_cover,
        financial_exposure: a.financial_exposure,
        shortage_volume: a.shortage_volume,
        status: a.status,
        timestamp: a.created_at,
        isLive: false,
      });
    }

    // 2. Real-time live alerts (override or add)
    for (const la of liveAlerts) {
      map.set(la.alert_id, {
        id: la.alert_id,
        supplier_id: la.supplier_id,
        component_sku: la.component_sku,
        risk_level: la.risk_level,
        days_of_cover: la.days_of_cover,
        gap_days: la.gap_days,
        shortage_volume: la.shortage_volume,
        financial_exposure: la.financial_exposure,
        status: la.status,
        hitl_required: la.hitl_required,
        hitl_tier: la.hitl_tier,
        timestamp: la.timestamp,
        isLive: true,
      });
    }

    const list = Array.from(map.values());

    // Sort descending by timestamp
    list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    // Apply feed filter
    return list.filter((item) => {
      if (feedFilter === 'CRITICAL') {
        return (item.risk_level || '').toUpperCase() === 'CRITICAL';
      }
      if (feedFilter === 'HITL') {
        return Boolean(item.hitl_required);
      }
      return true;
    });
  }, [alerts, liveAlerts, feedFilter]);

  const handleAcknowledge = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setAcknowledgingId(id);
      await onAcknowledgeAlert(id, 'Acknowledged via Risk Dashboard live feed');
    } finally {
      setAcknowledgingId(null);
    }
  };

  const formatExposure = (exp?: string | number | null): string => {
    if (exp == null) return '$0.00';
    const str = String(exp);
    const parts = str.split('.');
    const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const decimalPart = parts[1] || '00';
    return `$${integerPart}.${decimalPart}`;
  };

  const formatTimestamp = (iso: string): string => {
    try {
      const date = new Date(iso);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso;
    }
  };

  return (
    <div className="flex flex-col h-full rounded-xl border border-slate-800 bg-slate-900/90 shadow-xl backdrop-blur-md">
      {/* Feed Header */}
      <div className="p-4 border-b border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">Live Disruption Feed</h3>
          </div>

          {/* Connection Status Pill */}
          <div className="flex items-center gap-2">
            {isConnected ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-mono font-medium text-emerald-400 border border-emerald-500/20">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                MSK KAFKA LIVE
              </span>
            ) : isConnecting ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-mono font-medium text-amber-400 border border-amber-500/20">
                <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
                CONNECTING...
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-0.5 text-[11px] font-mono font-medium text-rose-400 border border-rose-500/20">
                <span className="h-2 w-2 rounded-full bg-rose-500" />
                OFFLINE
              </span>
            )}

            {liveAlerts.length > 0 && (
              <button
                type="button"
                onClick={onClearLiveAlerts}
                title="Clear live alert cache"
                className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 rounded-lg bg-slate-950/60 p-1 text-xs">
          <button
            type="button"
            onClick={() => setFeedFilter('ALL')}
            className={`flex-1 rounded py-1 font-medium transition-colors ${
              feedFilter === 'ALL'
                ? 'bg-slate-800 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            All Alerts ({unifiedAlerts.length})
          </button>
          <button
            type="button"
            onClick={() => setFeedFilter('CRITICAL')}
            className={`flex-1 rounded py-1 font-medium transition-colors ${
              feedFilter === 'CRITICAL'
                ? 'bg-rose-500/20 text-rose-300 font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Critical
          </button>
          <button
            type="button"
            onClick={() => setFeedFilter('HITL')}
            className={`flex-1 rounded py-1 font-medium transition-colors ${
              feedFilter === 'HITL'
                ? 'bg-indigo-500/20 text-indigo-300 font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            HITL Gates
          </button>
        </div>

        {wsError && (
          <p className="text-[11px] text-rose-400 font-mono">{wsError}</p>
        )}
      </div>

      {/* Alert Cards Scrollable List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5 max-h-[620px]">
        {unifiedAlerts.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            <Radio className="mx-auto h-7 w-7 text-slate-600 mb-2 animate-pulse" />
            <p className="font-medium text-slate-400">Listening on topic risk-alerts</p>
            <p className="mt-1 text-[11px] text-slate-500">
              New Kafka events will stream here automatically
            </p>
          </div>
        ) : (
          unifiedAlerts.map((item) => {
            const isSelected = selectedAlertId === item.id;
            const isCritical = (item.risk_level || '').toUpperCase() === 'CRITICAL';
            const isAcknowledged = item.status === 'ACKNOWLEDGED';

            return (
              <div
                key={item.id}
                onClick={() => onSelectAlert(isSelected ? null : item.id)}
                className={`group relative rounded-lg border p-3.5 transition-all cursor-pointer ${
                  isSelected
                    ? 'border-sky-500/80 bg-sky-950/40 shadow-md shadow-sky-500/10'
                    : isCritical
                    ? 'border-rose-500/30 bg-rose-950/20 hover:border-rose-500/50'
                    : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                }`}
              >
                {/* Header row: SKU, Severity, Timestamp */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs font-bold text-slate-100">
                      {item.component_sku}
                    </span>
                    {item.isLive && (
                      <span className="rounded bg-emerald-500/20 px-1 py-0.2 text-[9px] font-mono font-bold text-emerald-400 border border-emerald-500/30">
                        NEW
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase ${
                        isCritical
                          ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      }`}
                    >
                      {item.risk_level}
                    </span>
                    <span className="font-mono text-[10px] text-slate-400">
                      {formatTimestamp(item.timestamp)}
                    </span>
                  </div>
                </div>

                {/* Subtitle: Supplier ID */}
                {item.supplier_id && (
                  <p className="mt-1 font-mono text-[10px] text-slate-400 truncate">
                    Supplier: {item.supplier_id}
                  </p>
                )}

                {/* 2x2 Metric Grid */}
                <div className="mt-2.5 grid grid-cols-2 gap-2 rounded bg-slate-950/40 p-2 font-mono text-[11px]">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Days of Cover</span>
                    <span className="font-bold text-slate-200">
                      {item.days_of_cover != null ? `${Number(item.days_of_cover).toFixed(2)} d` : '--'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Exposure</span>
                    <span className="font-bold text-rose-300">
                      {formatExposure(item.financial_exposure)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Shortage</span>
                    <span className="text-slate-300">
                      {item.shortage_volume != null ? `${item.shortage_volume.toLocaleString()} u` : '--'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Shortage Gap</span>
                    <span className="text-slate-300">
                      {item.gap_days != null ? `${Number(item.gap_days).toFixed(2)} d` : '--'}
                    </span>
                  </div>
                </div>

                {/* Badges & Action Bar */}
                <div className="mt-2.5 flex items-center justify-between gap-2 pt-1 border-t border-slate-800/60">
                  <div className="flex items-center gap-1.5">
                    {item.hitl_required && (
                      <span className="inline-flex items-center gap-1 rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-indigo-400 border border-indigo-500/20">
                        <Lock className="h-2.5 w-2.5" />
                        {item.hitl_tier || 'HITL REQUIRED'}
                      </span>
                    )}

                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-mono ${
                        isAcknowledged
                          ? 'bg-slate-800 text-slate-400'
                          : 'bg-amber-500/10 text-amber-400'
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>

                  {!isAcknowledged && (
                    <button
                      type="button"
                      disabled={acknowledgingId === item.id}
                      onClick={(e) => handleAcknowledge(item.id, e)}
                      className="inline-flex items-center gap-1 rounded bg-sky-500/10 hover:bg-sky-500/20 px-2 py-0.5 text-[10px] font-semibold text-sky-400 border border-sky-500/30 transition-colors"
                    >
                      {acknowledgingId === item.id ? (
                        <RefreshCw className="h-3 w-3 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-3 w-3" />
                      )}
                      <span>Ack</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-slate-800 text-[10px] font-mono text-slate-500 flex justify-between items-center">
        <span>Topic: risk-alerts</span>
        <span>Auto-ack no-op safe</span>
      </div>
    </div>
  );
};
