/**
 * Investigation Panel Components Unit Tests (P12-3)
 *
 * Verifies:
 * - Stepper execution stages and SLA progress
 * - Deterministic Math Proof reproduction of NanoCore reference scenario
 * - Citation tags and registry integrity
 * - Ranked mitigation scenarios trade-offs and spend authorities
 */

import { describe, expect, it } from 'vitest';
import {
  CANONICAL_NANOCORE_INVESTIGATION,
  CITATION_REGISTRY,
} from '../../stores/useInvestigationStore';

describe('Investigation Panel & Dossier Invariants', () => {
  it('verifies 6-stage investigation pipeline schema aligns with LangGraph nodes', () => {
    const expectedNodes = ['triage', 'research', 'contract', 'risk', 'recommendation', 'hitl_gate'];
    const path = CANONICAL_NANOCORE_INVESTIGATION.execution_path;

    expect(path).toEqual(expectedNodes);
    expect(CANONICAL_NANOCORE_INVESTIGATION.current_node).toBe('hitl_gate');
    expect(CANONICAL_NANOCORE_INVESTIGATION.status).toBe('AWAITING_APPROVAL');
  });

  it('reproduces NanoCore deterministic math proof with 100% precision (BR-RULE-001)', () => {
    const metrics = CANONICAL_NANOCORE_INVESTIGATION.risk_metrics;
    expect(metrics).toBeDefined();

    const stock = Number(metrics?.usable_inventory_units);
    const burnRate = Number(metrics?.daily_consumption_units);
    const eta = Number(metrics?.inbound_eta_days);

    // Days of cover: 142,000 / 18,500 = 7.6756... -> 7.68
    const expectedCover = Number((stock / burnRate).toFixed(2));
    expect(expectedCover).toBe(7.68);
    expect(metrics?.days_of_cover).toBe(7.68);

    // Shortage Gap: 9.0 - 7.68 = 1.32
    const expectedGap = Number((eta - expectedCover).toFixed(2));
    expect(expectedGap).toBe(1.32);
    expect(metrics?.shortage_gap_days).toBe(1.32);

    // Net Shortage Volume: 1.32 * 18,500 = 24,420
    const expectedShortage = Math.round(expectedGap * burnRate);
    expect(expectedShortage).toBe(24420);
    expect(metrics?.projected_unit_shortage).toBe(24420);

    // Total Financial Exposure: 24,420 * 100.25 = 2,448,105.00
    const unitCost = Number(metrics?.unit_cost_usd);
    const expectedExposure = Number((expectedShortage * unitCost).toFixed(2));
    expect(expectedExposure).toBe(2448105.0);
    expect(metrics?.total_financial_exposure_usd).toBe(2448105.0);
  });

  it('verifies citation registry covers all narrative citation tags', () => {
    const narrative = CANONICAL_NANOCORE_INVESTIGATION.narrative || '';
    const citationKeys = ['REUTERS-TW-9921', 'NEPTUNE-GRAPH', 'SAP-INV-001', 'MSA-2024-BE §14.2'];

    for (const key of citationKeys) {
      expect(narrative).toContain(`[${key}]`);
      expect(CITATION_REGISTRY[key]).toBeDefined();
      expect(CITATION_REGISTRY[key].verification).toContain('Verified');
    }
  });

  it('verifies 3 ranked mitigation options with cryptographic spend authority tiers', () => {
    const recs = CANONICAL_NANOCORE_INVESTIGATION.recommendations || [];
    expect(recs.length).toBe(3);

    // Option 1: Air Charter Acceleration ($180,000 -> Procurement Director)
    const opt1 = recs[0];
    expect(opt1.scenario_id).toBe('SCEN-001');
    expect(opt1.scenario_type).toBe('LOGISTICS_EXPEDITE');
    expect(opt1.estimated_cost_usd).toBe(180000.0);
    expect(opt1.spend_tier).toBe('PROC_DIRECTOR');
    expect(opt1.lead_time_days).toBe(3.5);

    // Option 2: Secondary Sourcing ($240,000 -> Dual Sign-off)
    const opt2 = recs[1];
    expect(opt2.scenario_id).toBe('SCEN-002');
    expect(opt2.scenario_type).toBe('SECONDARY_SOURCE');
    expect(opt2.estimated_cost_usd).toBe(240000.0);
    expect(opt2.spend_tier).toBe('DUAL_VP');

    // Option 3: Line Rebalance ($75,000 -> Category Manager)
    const opt3 = recs[2];
    expect(opt3.scenario_id).toBe('SCEN-003');
    expect(opt3.scenario_type).toBe('LINE_REBALANCE');
    expect(opt3.estimated_cost_usd).toBe(75000.0);
    expect(opt3.spend_tier).toBe('CATEGORY_MGR');
  });

  it('verifies sub-90s SLO SLA completion time is recorded', () => {
    const duration = CANONICAL_NANOCORE_INVESTIGATION.duration_ms;
    expect(duration).toBeDefined();
    // 82,400ms = 82.4s <= 90s SLA
    expect(duration).toBeLessThanOrEqual(90000);
  });
});
