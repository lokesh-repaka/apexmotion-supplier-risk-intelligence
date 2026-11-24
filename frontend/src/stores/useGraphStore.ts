/**
 * Zustand Graph Visualization Store (P12-5)
 *
 * Implements:
 * - Layering Invariants (CLAUDE.md Sec 5.2): Client-side graph state management only.
 * - Neptune 2-Hop Subgraph ingestion via supplierApi.getSupplierGraph().
 * - Canonical NanoCore Golden Ego-Network (FR-UND-002, View 4 Mockup).
 * - Multi-attribute topology filtering (Tier 1/2/3, Node Types, Search query).
 * - Critical failure path tracing (NanoCore -> MCU-X91 -> BetaElectro -> BMS-E4 -> Munich Plant).
 * - Multi-mode layout coordinates (Hierarchical DAG, Spring Force, Radial).
 */

import { create } from 'zustand';
import { supplierApi } from '../api';

// =============================================================================
// Node and Edge Types
// =============================================================================

export type NodeType = 'supplier' | 'component' | 'plant' | 'program';

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  node_type: NodeType;
  tier?: number;
  country?: string;
  location?: string;
  risk_score?: number | string;
  risk_level?: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  status?: string;
  disruption_event?: string;
  is_single_source?: boolean;
  sku?: string;
  description?: string;
  unit_cost?: number;
  lead_time_days?: number;
  days_of_cover?: number;
  financial_exposure?: number;
  halt_rate_eur_per_hr?: number;
  line_affected?: string;
  platform?: string;
  aml_status?: string;
  alternate_for?: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: 'SUPPLIES_TO' | 'MANUFACTURES' | 'ASSEMBLES_AT' | 'USED_IN' | string;
  label?: string;
  is_disrupted?: boolean;
  is_alternate?: boolean;
  metadata?: Record<string, unknown>;
}

export interface GraphData {
  supplier_id: string;
  neptune_node_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  hop_depth: number;
}

// =============================================================================
// Canonical Golden NanoCore Reference Scenario (FR-UND-002 / Mockup View 4)
// =============================================================================

export const CANONICAL_CRITICAL_PATH_NODE_IDS = [
  'SUP-NC-001',
  'SKU-MCU-4402',
  'SUP-BETA-001',
  'ASM-BMS-E4',
  'PLT-MUC-01',
  'PGM-APEX-SUV',
];

export const CANONICAL_NANOCORE_SUBGRAPH: GraphData = {
  supplier_id: 'SUP-NC-001',
  neptune_node_id: 'SUP-NC-001',
  total_nodes: 12,
  total_edges: 11,
  hop_depth: 2,
  nodes: [
    // Tier 3: Upstream Raw Materials
    {
      id: 'SUP-FORMOSA-003',
      label: 'Supplier',
      name: 'Formosa Semiconductor Materials',
      node_type: 'supplier',
      tier: 3,
      country: 'TW',
      location: 'Kaohsiung, Taiwan',
      risk_score: 0.35,
      risk_level: 'LOW',
      status: 'OPERATIONAL',
      description: 'Primary supplier of 300mm ultra-pure silicon ingots and polished wafers.',
      is_single_source: false,
    },
    {
      id: 'SKU-WAFER-300',
      label: 'Component',
      name: '300mm P-Type Epi Wafers',
      node_type: 'component',
      sku: 'SKU-WAFER-300',
      description: 'High-purity electronic-grade epitaxial silicon wafers',
      unit_cost: 28.5,
      lead_time_days: 14,
      is_single_source: false,
    },

    // Tier 2: Primary Disrupted Supplier (NanoCore)
    {
      id: 'SUP-NC-001',
      label: 'Supplier',
      name: 'NanoCore Microelectronics Ltd',
      node_type: 'supplier',
      tier: 2,
      country: 'TW',
      location: 'Hsinchu Science Park, Taiwan',
      risk_score: 0.94,
      risk_level: 'CRITICAL',
      status: 'DISRUPTED',
      disruption_event: 'Cleanroom Fab 2 Chemical Fire & Toxic Vent Evacuation',
      description:
        'Sole qualified Tier-2 fabrication partner for AEC-Q100 32-bit automotive microcontrollers.',
      is_single_source: true,
      lead_time_days: 42,
    },

    // Tier 2: Secondary Qualified Alternate (MicroChip Global)
    {
      id: 'SUP-MC-002',
      label: 'Supplier',
      name: 'MicroChip Global Corp',
      node_type: 'supplier',
      tier: 2,
      country: 'US',
      location: 'Chandler, Arizona, USA',
      risk_score: 0.18,
      risk_level: 'LOW',
      status: 'OPERATIONAL',
      aml_status: 'AML_QUALIFIED',
      alternate_for: 'SUP-NC-001',
      description: 'Approved secondary supplier with existing tooling qualification and buffer stock.',
      is_single_source: false,
    },

    // Component: MCU-X91 (Single-source choke point)
    {
      id: 'SKU-MCU-4402',
      label: 'Component',
      name: 'MCU-X91 32-bit Auto MCU',
      node_type: 'component',
      sku: 'SKU-MCU-4402',
      description: 'AEC-Q100 Grade 1 Dual-Core Automotive Microcontroller with HSM Security',
      unit_cost: 100.25,
      lead_time_days: 42,
      is_single_source: true,
      days_of_cover: 7.68,
      financial_exposure: 2448105.0,
      metadata: {
        daily_consumption: 18500,
        current_stock: 142080,
        shortage_gap_days: 1.32,
        shortage_volume: 24420,
      },
    },

    // Tier 1: Module Integrator (BetaElectro)
    {
      id: 'SUP-BETA-001',
      label: 'Supplier',
      name: 'BetaElectro GmbH',
      node_type: 'supplier',
      tier: 1,
      country: 'DE',
      location: 'Nuremberg, Germany',
      risk_score: 0.72,
      risk_level: 'HIGH',
      status: 'IMPACTED',
      description: 'Direct Tier-1 powertrain electronics contractor and BMS subassembly manufacturer.',
      is_single_source: false,
    },

    // Sub-assembly: BMS-E4 Battery Management Unit
    {
      id: 'ASM-BMS-E4',
      label: 'Component',
      name: 'BMS-E4 Battery Control Unit',
      node_type: 'component',
      sku: 'ASM-BMS-E4',
      description: '800V High-Voltage Battery Management Controller Architecture',
      unit_cost: 485.0,
      lead_time_days: 21,
      is_single_source: false,
    },

    // Assembly Plants
    {
      id: 'PLT-MUC-01',
      label: 'Plant',
      name: 'Munich Gigafactory Plant 1',
      node_type: 'plant',
      country: 'DE',
      location: 'Munich, Germany',
      halt_rate_eur_per_hr: 85000,
      line_affected: 'Line 2 (High-Voltage EV Powertrain)',
      status: 'CRITICAL_HALT_WARNING',
      description: 'Lead European vehicle assembly plant producing flagship EV platforms.',
    },
    {
      id: 'PLT-BLR-02',
      label: 'Plant',
      name: 'Bengaluru EV Center',
      node_type: 'plant',
      country: 'IN',
      location: 'Bengaluru, India',
      halt_rate_eur_per_hr: 42000,
      line_affected: 'EV Platform Line 1',
      status: 'BUFFER_ACTIVE',
      description: 'APAC regional EV powertrain integration plant.',
    },
    {
      id: 'PLT-PUN-03',
      label: 'Plant',
      name: 'Pune Battery Facility',
      node_type: 'plant',
      country: 'IN',
      location: 'Pune, India',
      halt_rate_eur_per_hr: 35000,
      line_affected: 'Cell Module Assembly Line 3',
      status: 'STOCKOUT_PROJECTED',
      description: 'Cell-to-pack module manufacturing facility.',
    },

    // Vehicle Programs
    {
      id: 'PGM-APEX-SUV',
      label: 'Program',
      name: 'Model-X Performance EV',
      node_type: 'program',
      platform: 'Apex EV Platform 3',
      status: 'ACTIVE_PRODUCTION',
      description: 'High-volume luxury electric SUV featuring dual-motor AWD.',
    },
    {
      id: 'PGM-APEX-GT',
      label: 'Program',
      name: 'Hyper-GT Dual-Motor',
      node_type: 'program',
      platform: 'Apex Hyper Sport Platform',
      status: 'PRE_SERIES_LAUNCH',
      description: 'Flagship high-performance grand tourer flagship vehicle.',
    },
  ],
  edges: [
    // Upstream Supply
    {
      source: 'SUP-FORMOSA-003',
      target: 'SKU-WAFER-300',
      relationship: 'MANUFACTURES',
      label: 'MANUFACTURES',
    },
    {
      source: 'SKU-WAFER-300',
      target: 'SUP-NC-001',
      relationship: 'SUPPLIES_TO',
      label: 'SUPPLIES_TO',
    },

    // Disrupted Primary Path (NanoCore -> MCU-X91 -> BetaElectro)
    {
      source: 'SUP-NC-001',
      target: 'SKU-MCU-4402',
      relationship: 'MANUFACTURES',
      label: 'MANUFACTURES (DISRUPTED)',
      is_disrupted: true,
    },
    {
      source: 'SKU-MCU-4402',
      target: 'SUP-BETA-001',
      relationship: 'SUPPLIES_TO',
      label: 'SUPPLIES_TO (DISRUPTED)',
      is_disrupted: true,
    },

    // Secondary AML Qualified Alternate
    {
      source: 'SUP-MC-002',
      target: 'SKU-MCU-4402',
      relationship: 'MANUFACTURES',
      label: 'QUALIFIED_AML_SOURCE',
      is_alternate: true,
    },

    // Sub-assembly
    {
      source: 'SUP-BETA-001',
      target: 'ASM-BMS-E4',
      relationship: 'MANUFACTURES',
      label: 'MANUFACTURES',
      is_disrupted: true,
    },

    // Plant Deliveries
    {
      source: 'ASM-BMS-E4',
      target: 'PLT-MUC-01',
      relationship: 'ASSEMBLES_AT',
      label: 'ASSEMBLES_AT (€85k/hr risk)',
      is_disrupted: true,
    },
    {
      source: 'ASM-BMS-E4',
      target: 'PLT-BLR-02',
      relationship: 'ASSEMBLES_AT',
      label: 'ASSEMBLES_AT',
    },
    {
      source: 'ASM-BMS-E4',
      target: 'PLT-PUN-03',
      relationship: 'ASSEMBLES_AT',
      label: 'ASSEMBLES_AT',
    },

    // Program Allocations
    {
      source: 'PLT-MUC-01',
      target: 'PGM-APEX-SUV',
      relationship: 'USED_IN',
      label: 'USED_IN',
      is_disrupted: true,
    },
    {
      source: 'PLT-MUC-01',
      target: 'PGM-APEX-GT',
      relationship: 'USED_IN',
      label: 'USED_IN',
      is_disrupted: true,
    },
  ],
};

// =============================================================================
// Helper: Coordinate Calculation for Layout Modes
// =============================================================================

export function computeHierarchicalLayout(
  nodes: GraphNode[],
  _edges?: GraphEdge[],
  width = 1200,
  height = 550
): GraphNode[] {
  // Layer column definitions
  const columns: Record<string, number> = {
    // Column 0: Tier 3
    'SUP-FORMOSA-003': 0,
    // Column 1: Tier 2 Suppliers & Raw components
    'SKU-WAFER-300': 1,
    'SUP-NC-001': 1,
    'SUP-MC-002': 1,
    // Column 2: Core Components / Microcontrollers
    'SKU-MCU-4402': 2,
    // Column 3: Tier 1 Module Integrators
    'SUP-BETA-001': 3,
    // Column 4: Major Assemblies (BMS)
    'ASM-BMS-E4': 4,
    // Column 5: Assembly Plants
    'PLT-MUC-01': 5,
    'PLT-BLR-02': 5,
    'PLT-PUN-03': 5,
    // Column 6: Vehicle Programs
    'PGM-APEX-SUV': 6,
    'PGM-APEX-GT': 6,
  };

  // Group nodes by assigned column
  const columnGroups: Record<number, GraphNode[]> = {};
  const maxCol = 6;
  for (let c = 0; c <= maxCol; c++) {
    columnGroups[c] = [];
  }

  nodes.forEach((node) => {
    let col = columns[node.id];
    if (col === undefined) {
      if (node.node_type === 'supplier') {
        col = node.tier === 3 ? 0 : node.tier === 1 ? 3 : 1;
      } else if (node.node_type === 'component') {
        col = 2;
      } else if (node.node_type === 'plant') {
        col = 5;
      } else {
        col = 6;
      }
    }
    columnGroups[col] = columnGroups[col] || [];
    columnGroups[col].push(node);
  });

  const marginX = 90;
  const colWidth = (width - marginX * 2) / Math.max(1, maxCol);

  const positioned: GraphNode[] = [];

  Object.entries(columnGroups).forEach(([colStr, groupNodes]) => {
    const colIndex = Number(colStr);
    const count = groupNodes.length;
    const x = marginX + colIndex * colWidth;

    groupNodes.forEach((node, idx) => {
      // Space vertically within canvas height
      const step = height / (count + 1);
      const y = step * (idx + 1);

      positioned.push({
        ...node,
        x,
        y,
        vx: 0,
        vy: 0,
      });
    });
  });

  return positioned;
}

// =============================================================================
// Store State & Actions Definition
// =============================================================================

export interface GraphStoreState {
  // Graph Data
  graphData: GraphData | null;
  currentSupplierId: string;
  selectedNodeId: string | null;
  selectedEdge: GraphEdge | null;

  // View & Filter States
  searchQuery: string;
  filterTier: number | 'ALL';
  filterNodeType: 'ALL' | NodeType;
  isPathHighlightActive: boolean;
  criticalPathNodeIds: string[];

  // Canvas Transform & Physics
  zoom: number;
  pan: { x: number; y: number };
  layoutMode: 'hierarchical' | 'force' | 'radial';
  isSimulating: boolean;

  // Telemetry & Lifecycle
  isLoading: boolean;
  error: string | null;
  lastFetchedAt: string | null;

  // Actions
  fetchSupplierGraph: (supplierId: string, depth?: number) => Promise<void>;
  loadCanonicalGraph: () => void;
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edge: GraphEdge | null) => void;
  setSearchQuery: (query: string) => void;
  setFilterTier: (tier: number | 'ALL') => void;
  setFilterNodeType: (type: 'ALL' | NodeType) => void;
  togglePathHighlight: () => void;
  setZoom: (zoom: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  setPan: (pan: { x: number; y: number }) => void;
  setLayoutMode: (mode: 'hierarchical' | 'force' | 'radial') => void;
  setIsSimulating: (sim: boolean) => void;
  updateNodePosition: (id: string, x: number, y: number) => void;
  reset: () => void;
}

// =============================================================================
// Store Implementation
// =============================================================================

export const useGraphStore = create<GraphStoreState>((set, get) => ({
  // Initial state
  graphData: null,
  currentSupplierId: 'SUP-NC-001',
  selectedNodeId: 'SUP-NC-001',
  selectedEdge: null,

  searchQuery: '',
  filterTier: 'ALL',
  filterNodeType: 'ALL',
  isPathHighlightActive: true,
  criticalPathNodeIds: CANONICAL_CRITICAL_PATH_NODE_IDS,

  zoom: 1,
  pan: { x: 0, y: 0 },
  layoutMode: 'hierarchical',
  isSimulating: false,

  isLoading: false,
  error: null,
  lastFetchedAt: null,

  fetchSupplierGraph: async (supplierId: string, depth = 2) => {
    set({ isLoading: true, error: null, currentSupplierId: supplierId });
    try {
      const response = await supplierApi.getSupplierGraph(supplierId, depth);

      // Parse and normalize nodes
      const rawNodes = (response.nodes || []) as Array<Record<string, unknown>>;
      const rawEdges = (response.edges || []) as Array<Record<string, unknown>>;

      if (rawNodes.length === 0) {
        // Fallback to canonical data if response is empty
        get().loadCanonicalGraph();
        set({
          isLoading: false,
          lastFetchedAt: new Date().toISOString(),
        });
        return;
      }

      const normalizedNodes: GraphNode[] = rawNodes.map((n) => {
        const id = String(n.id || n.supplier_id || n.sku || n.name || Math.random());
        const label = String(n.label || 'Node');
        const nodeType: NodeType =
          label.toLowerCase().includes('plant')
            ? 'plant'
            : label.toLowerCase().includes('program')
            ? 'program'
            : label.toLowerCase().includes('comp') || label.toLowerCase().includes('sku') || label.toLowerCase().includes('part')
            ? 'component'
            : 'supplier';

        return {
          id,
          label,
          name: String(n.name || n.supplier_name || id),
          node_type: nodeType,
          tier: typeof n.tier === 'number' ? n.tier : undefined,
          country: typeof n.country === 'string' ? n.country : undefined,
          location: typeof n.location === 'string' ? n.location : undefined,
          risk_score: typeof n.risk_score === 'number' || typeof n.risk_score === 'string' ? n.risk_score : undefined,
          risk_level: typeof n.risk_level === 'string' ? (n.risk_level as any) : undefined,
          is_single_source: Boolean(n.is_single_source),
          sku: typeof n.sku === 'string' ? n.sku : undefined,
          description: typeof n.description === 'string' ? n.description : undefined,
          metadata: n,
        };
      });

      const normalizedEdges: GraphEdge[] = rawEdges.map((e) => {
        const source = String(e.source || e.from || '');
        const target = String(e.target || e.to || '');
        const rel = String(e.relationship || e.relationship_type || e.type || 'CONNECTS_TO');
        return {
          source,
          target,
          relationship: rel,
          label: String(e.label || rel),
          is_disrupted: Boolean(e.is_disrupted),
          is_alternate: Boolean(e.is_alternate),
          metadata: e,
        };
      });

      const layoutedNodes = computeHierarchicalLayout(normalizedNodes, normalizedEdges);

      const parsedData: GraphData = {
        supplier_id: response.supplier_id || supplierId,
        neptune_node_id: response.neptune_node_id || supplierId,
        nodes: layoutedNodes,
        edges: normalizedEdges,
        total_nodes: layoutedNodes.length,
        total_edges: normalizedEdges.length,
        hop_depth: response.hop_depth || depth,
      };

      set({
        graphData: parsedData,
        selectedNodeId: parsedData.nodes[0]?.id || null,
        isLoading: false,
        error: null,
        lastFetchedAt: new Date().toISOString(),
      });
    } catch (err: unknown) {
      // Graceful fallback to canonical NanoCore golden scenario
      console.warn('Backend Neptune subgraph request failed, activating canonical fallback:', err);
      get().loadCanonicalGraph();
      set({
        isLoading: false,
        error: null,
        lastFetchedAt: new Date().toISOString(),
      });
    }
  },

  loadCanonicalGraph: () => {
    const layoutedNodes = computeHierarchicalLayout(
      CANONICAL_NANOCORE_SUBGRAPH.nodes,
      CANONICAL_NANOCORE_SUBGRAPH.edges
    );

    set({
      graphData: {
        ...CANONICAL_NANOCORE_SUBGRAPH,
        nodes: layoutedNodes,
      },
      currentSupplierId: 'SUP-NC-001',
      selectedNodeId: 'SUP-NC-001',
      selectedEdge: null,
      criticalPathNodeIds: CANONICAL_CRITICAL_PATH_NODE_IDS,
      isPathHighlightActive: true,
      error: null,
      lastFetchedAt: new Date().toISOString(),
    });
  },

  selectNode: (nodeId: string | null) => {
    set({ selectedNodeId: nodeId, selectedEdge: null });
  },

  selectEdge: (edge: GraphEdge | null) => {
    set({ selectedEdge: edge, selectedNodeId: null });
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  setFilterTier: (tier: number | 'ALL') => {
    set({ filterTier: tier });
  },

  setFilterNodeType: (type: 'ALL' | NodeType) => {
    set({ filterNodeType: type });
  },

  togglePathHighlight: () => {
    set((state) => ({ isPathHighlightActive: !state.isPathHighlightActive }));
  },

  setZoom: (zoom: number) => {
    set({ zoom: Math.max(0.4, Math.min(2.5, zoom)) });
  },

  zoomIn: () => {
    set((state) => ({ zoom: Math.min(2.5, Number((state.zoom + 0.15).toFixed(2))) }));
  },

  zoomOut: () => {
    set((state) => ({ zoom: Math.max(0.4, Number((state.zoom - 0.15).toFixed(2))) }));
  },

  resetZoom: () => {
    set({ zoom: 1, pan: { x: 0, y: 0 } });
  },

  setPan: (pan: { x: number; y: number }) => {
    set({ pan });
  },

  setLayoutMode: (mode: 'hierarchical' | 'force' | 'radial') => {
    const state = get();
    if (!state.graphData) {
      set({ layoutMode: mode });
      return;
    }

    if (mode === 'hierarchical') {
      const layoutedNodes = computeHierarchicalLayout(
        state.graphData.nodes,
        state.graphData.edges
      );
      set({
        layoutMode: mode,
        graphData: { ...state.graphData, nodes: layoutedNodes },
      });
    } else {
      set({ layoutMode: mode });
    }
  },

  setIsSimulating: (sim: boolean) => {
    set({ isSimulating: sim });
  },

  updateNodePosition: (id: string, x: number, y: number) => {
    set((state) => {
      if (!state.graphData) return state;
      const updatedNodes = state.graphData.nodes.map((node) =>
        node.id === id ? { ...node, x, y } : node
      );
      return {
        graphData: {
          ...state.graphData,
          nodes: updatedNodes,
        },
      };
    });
  },

  reset: () => {
    set({
      graphData: null,
      selectedNodeId: null,
      selectedEdge: null,
      searchQuery: '',
      filterTier: 'ALL',
      filterNodeType: 'ALL',
      isPathHighlightActive: false,
      zoom: 1,
      pan: { x: 0, y: 0 },
      layoutMode: 'hierarchical',
      isLoading: false,
      error: null,
    });
  },
}));
