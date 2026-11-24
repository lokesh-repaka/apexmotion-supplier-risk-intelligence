/**
 * Graph Store Unit Tests (P12-5)
 *
 * Verifies:
 * - Default state initialization and reset.
 * - Loading canonical golden NanoCore ego-subgraph (FR-UND-002).
 * - Fetching graph data via supplierApi.getSupplierGraph().
 * - Fallback resilience when Neptune traversal API encounters error.
 * - Node and edge selection mechanics.
 * - Search query, tier, and node type filter transitions.
 * - Critical failure path toggling.
 * - Canvas zoom/pan boundaries and position updates.
 * - Multi-mode layout transformations (hierarchical, force, radial).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { supplierApi } from '../api/routes/suppliers';
import type { SupplierGraphResponse } from '../api/types';
import {
  CANONICAL_CRITICAL_PATH_NODE_IDS,
  CANONICAL_NANOCORE_SUBGRAPH,
  computeHierarchicalLayout,
  useGraphStore,
} from './useGraphStore';

describe('useGraphStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGraphStore.getState().reset();
  });

  it('initializes with clean default state upon reset()', () => {
    const state = useGraphStore.getState();
    expect(state.graphData).toBeNull();
    expect(state.selectedNodeId).toBeNull();
    expect(state.selectedEdge).toBeNull();
    expect(state.searchQuery).toBe('');
    expect(state.filterTier).toBe('ALL');
    expect(state.filterNodeType).toBe('ALL');
    expect(state.isPathHighlightActive).toBe(false);
    expect(state.zoom).toBe(1);
    expect(state.pan).toEqual({ x: 0, y: 0 });
    expect(state.layoutMode).toBe('hierarchical');
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('loads the canonical NanoCore golden scenario with 12 nodes and 11 edges', () => {
    useGraphStore.getState().loadCanonicalGraph();
    const state = useGraphStore.getState();

    expect(state.graphData).not.toBeNull();
    expect(state.graphData?.nodes.length).toBe(12);
    expect(state.graphData?.edges.length).toBe(11);
    expect(state.graphData?.supplier_id).toBe('SUP-NC-001');
    expect(state.selectedNodeId).toBe('SUP-NC-001');
    expect(state.isPathHighlightActive).toBe(true);
    expect(state.criticalPathNodeIds).toEqual(CANONICAL_CRITICAL_PATH_NODE_IDS);

    // Verify key NanoCore node attributes (BR-RULE-001 / Mockup View 4)
    const nanoCore = state.graphData?.nodes.find((n) => n.id === 'SUP-NC-001');
    expect(nanoCore).toBeDefined();
    expect(nanoCore?.name).toBe('NanoCore Microelectronics Ltd');
    expect(nanoCore?.tier).toBe(2);
    expect(nanoCore?.risk_score).toBe(0.94);
    expect(nanoCore?.status).toBe('DISRUPTED');
    expect(nanoCore?.is_single_source).toBe(true);

    // Verify MCU-X91 component node attributes
    const mcuNode = state.graphData?.nodes.find((n) => n.id === 'SKU-MCU-4402');
    expect(mcuNode).toBeDefined();
    expect(mcuNode?.node_type).toBe('component');
    expect(mcuNode?.days_of_cover).toBe(7.68);
    expect(mcuNode?.financial_exposure).toBe(2448105.0);

    // Verify Munich plant halt exposure
    const plantNode = state.graphData?.nodes.find((n) => n.id === 'PLT-MUC-01');
    expect(plantNode).toBeDefined();
    expect(plantNode?.halt_rate_eur_per_hr).toBe(85000);
  });

  it('computes valid coordinate layout in computeHierarchicalLayout()', () => {
    const positioned = computeHierarchicalLayout(
      CANONICAL_NANOCORE_SUBGRAPH.nodes,
      CANONICAL_NANOCORE_SUBGRAPH.edges,
      1200,
      600
    );

    expect(positioned.length).toBe(CANONICAL_NANOCORE_SUBGRAPH.nodes.length);
    positioned.forEach((node) => {
      expect(typeof node.x).toBe('number');
      expect(typeof node.y).toBe('number');
      expect(node.x).toBeGreaterThan(0);
      expect(node.y).toBeGreaterThan(0);
    });

    // Check that Tier-3 is left of Tier-2, and Plant is right of Tier-1
    const t3 = positioned.find((n) => n.id === 'SUP-FORMOSA-003');
    const t2 = positioned.find((n) => n.id === 'SUP-NC-001');
    const plant = positioned.find((n) => n.id === 'PLT-MUC-01');
    expect(t3!.x!).toBeLessThan(t2!.x!);
    expect(t2!.x!).toBeLessThan(plant!.x!);
  });

  it('fetches supplier subgraph via API successfully', async () => {
    const mockApiResponse: SupplierGraphResponse = {
      supplier_id: 'SUP-BETA-001',
      neptune_node_id: 'SUP-BETA-001',
      total_nodes: 2,
      total_edges: 1,
      hop_depth: 2,
      nodes: [
        {
          id: 'SUP-BETA-001',
          label: 'Supplier',
          name: 'BetaElectro GmbH',
          tier: 1,
          country: 'DE',
          risk_score: 0.72,
        },
        {
          id: 'PLT-MUC-01',
          label: 'Plant',
          name: 'Munich Plant',
        },
      ],
      edges: [
        {
          source: 'SUP-BETA-001',
          target: 'PLT-MUC-01',
          relationship: 'DELIVERS_TO',
          label: 'DELIVERS_TO',
        },
      ],
    };

    const spy = vi.spyOn(supplierApi, 'getSupplierGraph').mockResolvedValueOnce(mockApiResponse);

    await useGraphStore.getState().fetchSupplierGraph('SUP-BETA-001', 2);

    expect(spy).toHaveBeenCalledWith('SUP-BETA-001', 2);
    const state = useGraphStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.graphData?.supplier_id).toBe('SUP-BETA-001');
    expect(state.graphData?.nodes.length).toBe(2);
    expect(state.graphData?.edges.length).toBe(1);
    expect(state.selectedNodeId).toBe('SUP-BETA-001');
  });

  it('falls back gracefully to canonical golden data on API failure', async () => {
    vi.spyOn(supplierApi, 'getSupplierGraph').mockRejectedValueOnce(
      new Error('Neptune cluster connection timeout')
    );

    await useGraphStore.getState().fetchSupplierGraph('SUP-NC-001');

    const state = useGraphStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.graphData).not.toBeNull();
    expect(state.graphData?.nodes.length).toBe(12);
  });

  it('manages node and edge selections accurately', () => {
    useGraphStore.getState().loadCanonicalGraph();

    useGraphStore.getState().selectNode('SKU-MCU-4402');
    expect(useGraphStore.getState().selectedNodeId).toBe('SKU-MCU-4402');
    expect(useGraphStore.getState().selectedEdge).toBeNull();

    const sampleEdge = CANONICAL_NANOCORE_SUBGRAPH.edges[0];
    useGraphStore.getState().selectEdge(sampleEdge);
    expect(useGraphStore.getState().selectedEdge).toEqual(sampleEdge);
    expect(useGraphStore.getState().selectedNodeId).toBeNull();
  });

  it('toggles path highlighting and filter states', () => {
    expect(useGraphStore.getState().isPathHighlightActive).toBe(false);

    useGraphStore.getState().togglePathHighlight();
    expect(useGraphStore.getState().isPathHighlightActive).toBe(true);

    useGraphStore.getState().setSearchQuery('NanoCore');
    expect(useGraphStore.getState().searchQuery).toBe('NanoCore');

    useGraphStore.getState().setFilterTier(2);
    expect(useGraphStore.getState().filterTier).toBe(2);

    useGraphStore.getState().setFilterNodeType('component');
    expect(useGraphStore.getState().filterNodeType).toBe('component');
  });

  it('handles zoom in, zoom out, clamping, and reset', () => {
    useGraphStore.getState().setZoom(1.0);
    useGraphStore.getState().zoomIn();
    expect(useGraphStore.getState().zoom).toBe(1.15);

    useGraphStore.getState().zoomOut();
    expect(useGraphStore.getState().zoom).toBe(1.0);

    // Zoom upper clamp (2.5)
    useGraphStore.getState().setZoom(5.0);
    expect(useGraphStore.getState().zoom).toBe(2.5);

    // Zoom lower clamp (0.4)
    useGraphStore.getState().setZoom(0.1);
    expect(useGraphStore.getState().zoom).toBe(0.4);

    // Reset zoom and pan
    useGraphStore.getState().setPan({ x: 120, y: -45 });
    useGraphStore.getState().resetZoom();
    expect(useGraphStore.getState().zoom).toBe(1);
    expect(useGraphStore.getState().pan).toEqual({ x: 0, y: 0 });
  });

  it('updates individual node position on drag', () => {
    useGraphStore.getState().loadCanonicalGraph();

    useGraphStore.getState().updateNodePosition('SUP-NC-001', 345, 210);
    const updatedNode = useGraphStore
      .getState()
      .graphData?.nodes.find((n) => n.id === 'SUP-NC-001');

    expect(updatedNode?.x).toBe(345);
    expect(updatedNode?.y).toBe(210);
  });

  it('switches layout modes seamlessly', () => {
    useGraphStore.getState().loadCanonicalGraph();

    useGraphStore.getState().setLayoutMode('radial');
    expect(useGraphStore.getState().layoutMode).toBe('radial');

    useGraphStore.getState().setLayoutMode('force');
    expect(useGraphStore.getState().layoutMode).toBe('force');

    useGraphStore.getState().setLayoutMode('hierarchical');
    expect(useGraphStore.getState().layoutMode).toBe('hierarchical');
  });
});
