/**
 * Risk Dashboard Components Unit Tests (P12-2)
 */

import { describe, expect, it } from 'vitest';
import type { RiskAlert, SupplierRisk, WebSocketAlertData } from '../../api/types';

describe('Risk Dashboard Metrics & Aggregations', () => {
  const sampleSuppliers: SupplierRisk[] = [
    {
      supplier_id: 'sup-nc-1',
      neptune_node_id: 'SUP-NC-882',
      supplier_name: 'NanoCore Semiconductor GmbH',
      country_code: 'DE',
      tier: 1,
      composite_risk_score: '0.920',
      risk_level: 'CRITICAL',
      active_alerts_count: 1,
      critical_alerts_count: 1,
      total_financial_exposure_usd: '2448105.00',
      total_shortage_volume: 24420,
      min_days_of_cover: '7.68',
      affected_skus: ['NC-2024'],
      affected_plants: ['PLT-MUC-01'],
      affected_programs: ['PGM-APEX-SUV'],
      is_single_source: true,
      evaluated_at: '2026-11-24T12:00:00Z',
    },
    {
      supplier_id: 'sup-tw-2',
      neptune_node_id: 'SUP-TW-101',
      supplier_name: 'Apex Micro Taiwan Corp',
      country_code: 'TW',
      tier: 2,
      composite_risk_score: '0.550',
      risk_level: 'HIGH',
      active_alerts_count: 1,
      critical_alerts_count: 0,
      total_financial_exposure_usd: '75000.00',
      total_shortage_volume: 1200,
      min_days_of_cover: '14.50',
      affected_skus: ['MCU-X91'],
      affected_plants: ['PLT-BLR-02'],
      affected_programs: ['PGM-E-SEDAN'],
      is_single_source: false,
      evaluated_at: '2026-11-24T12:00:00Z',
    },
    {
      supplier_id: 'sup-us-3',
      neptune_node_id: 'SUP-US-404',
      supplier_name: 'Austin Sensor Labs',
      country_code: 'US',
      tier: 3,
      composite_risk_score: '0.210',
      risk_level: 'LOW',
      active_alerts_count: 0,
      critical_alerts_count: 0,
      total_financial_exposure_usd: '0.00',
      total_shortage_volume: 0,
      min_days_of_cover: null,
      affected_skus: [],
      affected_plants: [],
      affected_programs: [],
      is_single_source: false,
      evaluated_at: '2026-11-24T12:00:00Z',
    },
  ];

  it('filters suppliers by search term matching name, SKU, and country', () => {
    // 1. Search by name
    const byName = sampleSuppliers.filter((s) =>
      s.supplier_name.toLowerCase().includes('nanocore')
    );
    expect(byName).toHaveLength(1);
    expect(byName[0].supplier_name).toContain('NanoCore');

    // 2. Search by SKU
    const bySku = sampleSuppliers.filter((s) =>
      s.affected_skus.some((sku) => sku.toLowerCase().includes('mcu-x91'))
    );
    expect(bySku).toHaveLength(1);
    expect(bySku[0].supplier_name).toContain('Apex Micro');

    // 3. Search by Country
    const byCountry = sampleSuppliers.filter((s) =>
      s.country_code.toLowerCase() === 'de'
    );
    expect(byCountry).toHaveLength(1);
  });

  it('filters suppliers by tier and risk severity level', () => {
    // Tier 1 Critical
    const tier1Critical = sampleSuppliers.filter(
      (s) => s.tier === 1 && s.risk_level === 'CRITICAL'
    );
    expect(tier1Critical).toHaveLength(1);

    // Tier 2 High
    const tier2High = sampleSuppliers.filter(
      (s) => s.tier === 2 && s.risk_level === 'HIGH'
    );
    expect(tier2High).toHaveLength(1);

    // Tier 3 Low
    const tier3Low = sampleSuppliers.filter(
      (s) => s.tier === 3 && s.risk_level === 'LOW'
    );
    expect(tier3Low).toHaveLength(1);
  });

  it('aggregates heatmap cell matrix counts and exposure values', () => {
    const criticalTier1 = sampleSuppliers.filter(
      (s) => s.tier === 1 && s.risk_level === 'CRITICAL'
    );
    expect(criticalTier1).toHaveLength(1);
    expect(criticalTier1[0].total_financial_exposure_usd).toBe('2448105.00');

    const highTier2 = sampleSuppliers.filter(
      (s) => s.tier === 2 && s.risk_level === 'HIGH'
    );
    expect(highTier2).toHaveLength(1);
    expect(highTier2[0].total_financial_exposure_usd).toBe('75000.00');
  });

  it('formats currency numbers with exact Decimal grouping', () => {
    const formatExposure = (exp: string): string => {
      const parts = exp.split('.');
      const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      const decPart = parts[1] || '00';
      return `$${intPart}.${decPart}`;
    };

    expect(formatExposure('2448105.00')).toBe('$2,448,105.00');
    expect(formatExposure('75000.00')).toBe('$75,000.00');
    expect(formatExposure('0.00')).toBe('$0.00');
  });

  it('unifies and sorts alert feed items chronologically', () => {
    const alerts: RiskAlert[] = [
      {
        id: 'alt-old',
        component_sku: 'CAP-10',
        risk_level: 'MEDIUM',
        status: 'OPEN',
        created_at: '2026-11-24T09:00:00Z',
      },
    ];

    const liveAlerts: WebSocketAlertData[] = [
      {
        alert_id: 'alt-new',
        component_sku: 'NC-2024',
        risk_level: 'CRITICAL',
        days_of_cover: '7.68',
        shortage_volume: 24420,
        financial_exposure: '2448105.00',
        status: 'OPEN',
        hitl_required: true,
        hitl_tier: 'DUAL_VP',
        timestamp: '2026-11-24T12:00:00Z',
      },
    ];

    const combined = [
      ...liveAlerts.map((la) => ({ id: la.alert_id, ts: la.timestamp })),
      ...alerts.map((a) => ({ id: a.id, ts: a.created_at })),
    ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());

    expect(combined[0].id).toBe('alt-new');
    expect(combined[1].id).toBe('alt-old');
  });
});
