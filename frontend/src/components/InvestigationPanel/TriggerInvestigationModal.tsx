/**
 * Trigger Investigation Modal Component (P12-3)
 *
 * Allows users to trigger an automated sub-90s multi-agent investigation:
 * - Submits POST /api/v1/investigations/start
 * - Accepts supplier ID, component SKU, signal type, and raw signal text
 * - Supports pre-filling with canonical reference scenarios
 */

import React, { useState } from 'react';
import { Play, RotateCw, Sparkles, X, Zap } from 'lucide-react';
import type { InvestigationStartRequest } from '../../api/types';

interface TriggerInvestigationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (req: InvestigationStartRequest) => Promise<void>;
  isSubmitting: boolean;
  defaultSupplierId?: string;
}

export const TriggerInvestigationModal: React.FC<TriggerInvestigationModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting,
  defaultSupplierId,
}) => {
  const [supplierId, setSupplierId] = useState(defaultSupplierId || 'SUP-NC-001');
  const [componentSku, setComponentSku] = useState('SKU-MCU-4402');
  const [signalType, setSignalType] = useState('news');
  const [rawSignal, setRawSignal] = useState(
    'Taiwan Fire Agency reports industrial electrical fire at NanoCore Semiconductor Fab 2 in Hsinchu. Diffusion lines halted with cleanroom seal breach. Estimated shutdown 21 days.'
  );
  const [waitForCompletion, setWaitForCompletion] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!supplierId.trim()) {
      setError('Supplier ID is required');
      return;
    }

    try {
      await onSubmit({
        supplier_id: supplierId.trim(),
        component_sku: componentSku.trim() || undefined,
        signal_type: signalType,
        raw_signal: rawSignal.trim(),
        wait_for_completion: waitForCompletion,
      });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to launch investigation');
    }
  };

  const handlePreFillNanoCore = () => {
    setSupplierId('SUP-NC-001');
    setComponentSku('SKU-MCU-4402');
    setSignalType('news');
    setRawSignal(
      'Taiwan Fire Agency reports industrial electrical fire at NanoCore Semiconductor Fab 2 in Hsinchu. Diffusion lines halted with cleanroom seal breach. Estimated shutdown 21 days.'
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-[#0c111d] p-6 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
              <Zap className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">
                Launch Automated Risk Investigation
              </h3>
              <p className="text-[11px] text-slate-400">
                Multi-Agent Detective Workflow (SLO p95 &le; 90s)
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Pre-fill quick button */}
        <div className="flex justify-between items-center rounded-lg bg-sky-500/10 border border-sky-500/20 p-2.5 text-xs text-sky-300">
          <span>Test Reference Scenario:</span>
          <button
            type="button"
            onClick={handlePreFillNanoCore}
            className="flex items-center gap-1 rounded bg-sky-600 hover:bg-sky-500 px-2.5 py-1 text-[11px] font-bold text-white transition-colors"
          >
            <Sparkles className="h-3 w-3" />
            <span>Load NanoCore Cleanroom Fire</span>
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Supplier ID & Component SKU */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Supplier ID <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value)}
                placeholder="SUP-NC-001"
                className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Component SKU
              </label>
              <input
                type="text"
                value={componentSku}
                onChange={(e) => setComponentSku(e.target.value)}
                placeholder="SKU-MCU-4402"
                className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>

          {/* Signal Type */}
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Disruption Taxonomy
            </label>
            <select
              value={signalType}
              onChange={(e) => setSignalType(e.target.value)}
              className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500"
            >
              <option value="news">External News / Public Telemetry</option>
              <option value="financial">Financial / Insolvency Disclosures</option>
              <option value="logistics">Maritime AIS / Freight Disruptions</option>
              <option value="geopolitical">Trade / Regulatory Sanctions</option>
            </select>
          </div>

          {/* Raw Signal Text */}
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Raw Disruption Signal (Sanitized via Quarantined Reader)
            </label>
            <textarea
              rows={3}
              value={rawSignal}
              onChange={(e) => setRawSignal(e.target.value)}
              placeholder="Paste raw news snippet, sensor alert, or vendor advisory..."
              className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500"
            />
          </div>

          {/* Execution Mode */}
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="waitCheck"
              checked={waitForCompletion}
              onChange={(e) => setWaitForCompletion(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-sky-500 focus:ring-0"
            />
            <label htmlFor="waitCheck" className="text-xs text-slate-400 cursor-pointer">
              Wait for synchronous completion (instead of asynchronous background polling)
            </label>
          </div>

          {/* Footer Buttons */}
          <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-lg bg-slate-800 hover:bg-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-sky-600/20 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <RotateCw className="h-3.5 w-3.5 animate-spin" />
                  <span>Launching Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5 fill-current" />
                  <span>Launch Investigation (Sub-90s) &rarr;</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
