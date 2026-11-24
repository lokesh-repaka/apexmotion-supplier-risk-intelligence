/**
 * Supplier Graph Visualization Invariants & Unit Tests (P12-5)
 *
 * Verifies:
 * - Topological Invariants & Neptune 2-Hop Traversal (FR-UND-002 / Mockup View 4).
 * - Canonical NanoCore multi-tier ego-network integrity across Tier 1, 2, 3, Components, Plants, and Programs.
 * - Critical failure path tracing (NanoCore -> MCU-X91 -> BetaElectro -> BMS-E4 -> Munich -> Model-X).
 * - Qualified AML alternate route bypass (MicroChip Global).
 * - Strict adherence to deterministic arithmetic invariants (BR-RULE-001).
 * - Hierarchical DAG and radial blast radius coordinate geometry.
 * - Upstream feeder and downstream consumer neighborhood resolution.
 */

import { describe, expect, it } from 'vitest';
import {
  CANONICAL_CRITICAL_PATH_NODE_IDS,
  CANONICAL_NANOCORE_SUBGRAPH,
  computeHierarchicalLayout,
} from '../../stores/useGraphStore';

describe('Supplier Graph Visualizer & Neptune Subgraph Invariants (P12-5)', () => {
  it('enforces 2-hop topological ego-subgraph entity coverage (FR-UND-002)', () => {
    const { nodes } = CANONICAL_NANOCORE_SUBGRAPH;

    // Verify entity distribution across tiers and types
    const nodeTypes = new Set(nodes.map((n) => n.node_type));
    expect(nodeTypes).toContain('supplier');
    expect(nodeTypes).toContain('component');
    expect(nodeTypes).toContain('plant');
    expect(nodeTypes).toContain('program');

    // Supplier Tiers
    const suppliers = nodes.filter((n) => n.node_type === 'supplier');
    const tiers = suppliers.map((s) => s.tier);
    expect(tiers).toContain(1); // BetaElectro
    expect(tiers).toContain(2); // NanoCore, MicroChip
    expect(tiers).toContain(3); // Formosa Silicon

    // Plants & Assembly Facilities
    const plants = nodes.filter((n) => n.node_type === 'plant');
    expect(plants.length).toBe(3);
    const plantIds = plants.map((p) => p.id);
    expect(plantIds).toContain('PLT-MUC-01');
    expect(plantIds).toContain('PLT-BLR-02');
    expect(plantIds).toContain('PLT-PUN-03');

    // Vehicle Programs
    const programs = nodes.filter((n) => n.node_type === 'program');
    expect(programs.length).toBe(2);
    const progIds = programs.map((p) => p.id);
    expect(progIds).toContain('PGM-APEX-SUV');
    expect(progIds).toContain('PGM-APEX-GT');
  });

  it('validates canonical critical failure path unbroken chain of edges', () => {
    const { edges } = CANONICAL_NANOCORE_SUBGRAPH;
    const path = CANONICAL_CRITICAL_PATH_NODE_IDS;

    // Must be 6 nodes forming 5 consecutive hops
    expect(path.length).toBe(6);

    for (let i = 0; i < path.length - 1; i++) {
      const src = path[i];
      const tgt = path[i + 1];

      const matchingEdge = edges.find(
        (e) => e.source === src && e.target === tgt
      );
      expect(
        matchingEdge,
        `Expected failure path edge from ${src} to ${tgt}`
      ).toBeDefined();
      expect(matchingEdge?.is_disrupted).toBe(true);
    }
  });

  it('verifies Qualified AML Alternate route bypasses disrupted NanoCore fab', () => {
    const { edges } = CANONICAL_NANOCORE_SUBGRAPH;

    // MicroChip Global (SUP-MC-002) manufactures MCU-X91 without touching NanoCore
    const altEdge = edges.find(
      (e) => e.source === 'SUP-MC-002' && e.target === 'SKU-MCU-4402'
    );

    expect(altEdge).toBeDefined();
    expect(altEdge?.is_alternate).toBe(true);
    expect(altEdge?.relationship).toBe('MANUFACTURES');
    expect(altEdge?.is_disrupted).toBeFalsy();
  });

  it('reproduces NanoCore deterministic financial and line halt exposure (BR-RULE-001)', () => {
    const { nodes } = CANONICAL_NANOCORE_SUBGRAPH;

    // MCU-X91 component metrics
    const mcu = nodes.find((n) => n.id === 'SKU-MCU-4402');
    expect(mcu).toBeDefined();
    expect(mcu?.is_single_source).toBe(true);
    expect(mcu?.days_of_cover).toBe(7.68);
    expect(mcu?.unit_cost).toBe(100.25);

    const meta = mcu?.metadata as {
      daily_consumption: number;
      current_stock: number;
      shortage_gap_days: number;
      shortage_volume: number;
    };
    expect(meta.daily_consumption).toBe(18500);
    expect(meta.current_stock).toBe(142080);
    expect(meta.shortage_gap_days).toBe(1.32);
    expect(meta.shortage_volume).toBe(24420);

    // Financial Exposure: 24,420 * $100.25 = $2,448,105.00
    expect(mcu?.financial_exposure).toBe(2448105.0);

    // Munich Gigafactory halt rate: €85,000/hr
    const munich = nodes.find((n) => n.id === 'PLT-MUC-01');
    expect(munich).toBeDefined();
    expect(munich?.halt_rate_eur_per_hr).toBe(85000);
    expect(munich?.status).toBe('CRITICAL_HALT_WARNING');
  });

  it('computes hierarchical layout with strictly monotonic tier column coordinates', () => {
    const { nodes, edges } = CANONICAL_NANOCORE_SUBGRAPH;
    const positioned = computeHierarchicalLayout(nodes, edges, 1400, 650);

    const getX = (id: string) => positioned.find((n) => n.id === id)?.x ?? 0;

    const t3X = getX('SUP-FORMOSA-003');
    const t2X = getX('SUP-NC-001');
    const compX = getX('SKU-MCU-4402');
    const t1X = getX('SUP-BETA-001');
    const asmX = getX('ASM-BMS-E4');
    const pltX = getX('PLT-MUC-01');
    const pgmX = getX('PGM-APEX-SUV');

    // Monotonic left-to-right progression
    expect(t3X).toBeLessThan(t2X);
    expect(t2X).toBeLessThan(compX);
    expect(compX).toBeLessThan(t1X);
    expect(t1X).toBeLessThan(asmX);
    expect(asmX).toBeLessThan(pltX);
    expect(pltX).toBeLessThan(pgmX);
  });

  it('resolves correct upstream and downstream topology for choke point SKU-MCU-4402', () => {
    const { edges } = CANONICAL_NANOCORE_SUBGRAPH;
    const targetSku = 'SKU-MCU-4402';

    // Upstream feeders to SKU-MCU-4402 (NanoCore primary + MicroChip secondary)
    const upstream = edges
      .filter((e) => e.target === targetSku)
      .map((e) => e.source);

    expect(upstream).toContain('SUP-NC-001');
    expect(upstream).toContain('SUP-MC-002');
    expect(upstream.length).toBe(2);

    // Downstream consumers from SKU-MCU-4402 (BetaElectro Tier-1)
    const downstream = edges
      .filter((e) => e.source === targetSku)
      .map((e) => e.target);

    expect(downstream).toContain('SUP-BETA-001');
    expect(downstream.length).toBe(1);
  });
});
