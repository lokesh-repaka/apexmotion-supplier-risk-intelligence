/**
 * Supplier Risk Table Component (P12-2)
 *
 * Displays multi-tier supplier risk ratings, inventory cover, and financial exposure:
 * - Real-time filtering by supplier name, component SKU, tier, and severity level.
 * - Exact Decimal formatting for monetary exposure and days of cover.
 * - Visual risk score meters (0.000 to 1.000).
 * - Blast radius tags (impacted assembly plants and vehicle programs).
 * - Row selection and investigation trigger hooks.
 */

import React, { useMemo } from 'react';
import {
  AlertCircle,
  Building2,
  ChevronRight,
  Search,
} from 'lucide-react';
import type { SupplierRisk } from '../../api/types';
import type { RiskFilterState } from '../../stores/useRiskStore';

interface SupplierRiskTableProps {
  suppliers: SupplierRisk[];
  selectedSupplierId: string | null;
  onSelectSupplier: (id: string | null) => void;
  filters: RiskFilterState;
  onFilterChange: (filters: Partial<RiskFilterState>) => void;
  isLoading?: boolean;
}

export const SupplierRiskTable: React.FC<SupplierRiskTableProps> = ({
  suppliers,
  selectedSupplierId,
  onSelectSupplier,
  filters,
  onFilterChange,
  isLoading = false,
}) => {
  // Filter suppliers by search query, severity, and tier
  const filteredSuppliers = useMemo(() => {
    return suppliers.filter((s) => {
      // 1. Search filter (name, node_id, country, or affected SKUs)
      if (filters.search.trim()) {
        const query = filters.search.toLowerCase().trim();
        const matchesName = s.supplier_name.toLowerCase().includes(query);
        const matchesNode = (s.neptune_node_id || '').toLowerCase().includes(query);
        const matchesCountry = s.country_code.toLowerCase().includes(query);
        const matchesSku = s.affected_skus.some((sku) => sku.toLowerCase().includes(query));
        if (!matchesName && !matchesNode && !matchesCountry && !matchesSku) {
          return false;
        }
      }

      // 2. Risk Level filter
      if (filters.riskLevel !== 'ALL') {
        if ((s.risk_level || '').toUpperCase() !== filters.riskLevel) {
          return false;
        }
      }

      // 3. Tier filter
      if (filters.tier !== null) {
        if (s.tier !== filters.tier) {
          return false;
        }
      }

      return true;
    });
  }, [suppliers, filters]);

  const getSeverityBadge = (level: string) => {
    const norm = (level || '').toUpperCase();
    switch (norm) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 px-2 py-0.5 text-xs font-semibold text-rose-400 border border-rose-500/30">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-400 border border-amber-500/30">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            HIGH
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-yellow-500/20 px-2 py-0.5 text-xs font-semibold text-yellow-400 border border-yellow-500/30">
            MEDIUM
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-500/30">
            LOW
          </span>
        );
    }
  };

  const formatExposure = (exp: string | number): string => {
    const str = String(exp);
    const parts = str.split('.');
    const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const decimalPart = parts[1] || '00';
    return `$${integerPart}.${decimalPart}`;
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 shadow-xl backdrop-blur-md">
      {/* Header & Filter Controls */}
      <div className="flex flex-col gap-4 border-b border-slate-800 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-sky-500/10 p-2 text-sky-400">
            <Building2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Supplier Risk Matrix
            </h2>
            <p className="text-xs text-slate-400">
              Live composite risk ratings across Tier 1–3 supply chains
            </p>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search Box */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search supplier, SKU, country..."
              value={filters.search}
              onChange={(e) => onFilterChange({ search: e.target.value })}
              className="h-9 w-48 rounded-lg border border-slate-700 bg-slate-800/80 pl-9 pr-3 text-xs text-slate-200 placeholder-slate-400 focus:border-sky-500 focus:outline-none sm:w-60"
            />
          </div>

          {/* Risk Level Filter Dropdown */}
          <div className="relative flex items-center">
            <select
              value={filters.riskLevel}
              onChange={(e) =>
                onFilterChange({
                  riskLevel: e.target.value as RiskFilterState['riskLevel'],
                })
              }
              className="h-9 rounded-lg border border-slate-700 bg-slate-800/80 px-3 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical Only</option>
              <option value="HIGH">High Only</option>
              <option value="MEDIUM">Medium Only</option>
              <option value="LOW">Low Only</option>
            </select>
          </div>

          {/* Tier Filter Dropdown */}
          <div className="relative flex items-center">
            <select
              value={filters.tier !== null ? String(filters.tier) : 'ALL'}
              onChange={(e) => {
                const val = e.target.value;
                onFilterChange({ tier: val === 'ALL' ? null : parseInt(val, 10) });
              }}
              className="h-9 rounded-lg border border-slate-700 bg-slate-800/80 px-3 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value="ALL">All Tiers</option>
              <option value="1">Tier 1 (Direct OEM)</option>
              <option value="2">Tier 2 (Sub-tier)</option>
              <option value="3">Tier 3 (Raw Materials)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/40 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
            <tr>
              <th scope="col" className="px-5 py-3.5">
                Supplier & Identifier
              </th>
              <th scope="col" className="px-4 py-3.5">
                Tier / Region
              </th>
              <th scope="col" className="px-4 py-3.5">
                Risk Score
              </th>
              <th scope="col" className="px-4 py-3.5">
                Severity
              </th>
              <th scope="col" className="px-4 py-3.5">
                Coverage & Shortage
              </th>
              <th scope="col" className="px-4 py-3.5">
                Financial Exposure
              </th>
              <th scope="col" className="px-4 py-3.5">
                Blast Radius
              </th>
              <th scope="col" className="px-4 py-3.5 text-right">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-sans">
            {isLoading ? (
              // Loading Skeleton Rows
              Array.from({ length: 4 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="px-5 py-4">
                    <div className="h-4 w-36 rounded bg-slate-800" />
                    <div className="mt-1 h-3 w-20 rounded bg-slate-800/60" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-14 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-20 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-16 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-24 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-20 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="h-4 w-28 rounded bg-slate-800" />
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="ml-auto h-6 w-16 rounded bg-slate-800" />
                  </td>
                </tr>
              ))
            ) : filteredSuppliers.length === 0 ? (
              // Empty State
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400">
                  <AlertCircle className="mx-auto h-8 w-8 text-slate-500 mb-2" />
                  <p className="text-sm font-medium text-slate-300">
                    No suppliers match current filters
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Try adjusting your search criteria or resetting filters
                  </p>
                </td>
              </tr>
            ) : (
              // Populated Supplier Rows
              filteredSuppliers.map((s) => {
                const isSelected = selectedSupplierId === s.supplier_id;
                const scoreNum = parseFloat(String(s.composite_risk_score)) || 0;
                const scorePercent = Math.min(Math.max(scoreNum * 100, 0), 100);

                return (
                  <tr
                    key={s.supplier_id}
                    onClick={() => onSelectSupplier(isSelected ? null : s.supplier_id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-sky-950/40 border-l-2 border-l-sky-400'
                        : 'hover:bg-slate-800/50'
                    }`}
                  >
                    {/* Supplier Name & Identifiers */}
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100">
                          {s.supplier_name}
                        </span>
                        {s.is_single_source && (
                          <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-bold text-rose-400 border border-rose-500/20">
                            Single Source
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-slate-400">
                        <span>{s.neptune_node_id || s.supplier_id.slice(0, 8)}</span>
                      </div>
                    </td>

                    {/* Tier / Country */}
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-1.5">
                        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                          Tier {s.tier}
                        </span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-400">
                          {s.country_code}
                        </span>
                      </div>
                    </td>

                    {/* Composite Risk Score */}
                    <td className="px-4 py-4">
                      <div className="w-24">
                        <div className="flex justify-between font-mono text-[11px] mb-1">
                          <span className="text-slate-300 font-bold">
                            {Number(scoreNum).toFixed(3)}
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              scoreNum >= 0.7
                                ? 'bg-rose-500'
                                : scoreNum >= 0.4
                                ? 'bg-amber-400'
                                : 'bg-emerald-400'
                            }`}
                            style={{ width: `${scorePercent}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Severity Badge */}
                    <td className="px-4 py-4">{getSeverityBadge(s.risk_level)}</td>

                    {/* Coverage & Shortage */}
                    <td className="px-4 py-4 font-mono text-[11px]">
                      {s.min_days_of_cover != null ? (
                        <>
                          <div className="font-bold text-slate-200">
                            {Number(s.min_days_of_cover).toFixed(2)} d cover
                          </div>
                          <div className="text-slate-400 text-[10px]">
                            {s.total_shortage_volume.toLocaleString()} units short
                          </div>
                        </>
                      ) : (
                        <span className="text-slate-500">Buffer intact</span>
                      )}
                    </td>

                    {/* Financial Exposure */}
                    <td className="px-4 py-4 font-mono text-[11px] font-semibold text-rose-300">
                      {formatExposure(s.total_financial_exposure_usd)}
                    </td>

                    {/* Blast Radius */}
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-1 max-w-[180px]">
                        {s.affected_skus.slice(0, 2).map((sku) => (
                          <span
                            key={sku}
                            className="rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-sky-300 border border-slate-700"
                          >
                            {sku}
                          </span>
                        ))}
                        {s.affected_plants.slice(0, 1).map((plt) => (
                          <span
                            key={plt}
                            className="rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300 border border-slate-700"
                          >
                            {plt}
                          </span>
                        ))}
                        {s.affected_skus.length === 0 && (
                          <span className="text-slate-500 text-[10px]">None</span>
                        )}
                      </div>
                    </td>

                    {/* Select / Investigate */}
                    <td className="px-4 py-4 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectSupplier(s.supplier_id);
                        }}
                        className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                          isSelected
                            ? 'bg-sky-500 text-white'
                            : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
                        }`}
                      >
                        <span>{isSelected ? 'Selected' : 'Inspect'}</span>
                        <ChevronRight className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer Counter */}
      <div className="flex items-center justify-between border-t border-slate-800 px-5 py-3 text-xs text-slate-400">
        <span>
          Showing <span className="font-semibold text-slate-200">{filteredSuppliers.length}</span> of{' '}
          <span className="font-semibold text-slate-200">{suppliers.length}</span> suppliers
        </span>
        <span className="font-mono text-[11px] text-slate-500">
          Aurora PostgreSQL · Neptune Graph Topology
        </span>
      </div>
    </div>
  );
};
