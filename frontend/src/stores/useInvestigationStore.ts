/**
 * Investigation Zustand Store (P12-3)
 *
 * Coordinates multi-agent investigation lifecycle:
 * - Triggering new automated sub-90s investigations (POST /api/v1/investigations/start)
 * - Autonomous polling of progress, active LangGraph node, and final dossier (GET /api/v1/investigations/{id})
 * - Canonical NanoCore reference scenario fallback state (Zero Hallucination / FRD FR-DEC-001)
 * - Circuit breaker fallback / Graceful degradation simulation (FR-DEC-001 Alt Flow)
 * - Interactive evidence citation registry & modal state
 */

import { create } from 'zustand';
import { investigationApi } from '../api/routes/investigations';
import type {
  InvestigationDetailResponse,
  InvestigationStartRequest,
  InvestigationStartResponse,
} from '../api/types';

// =============================================================================
// Citation Metadata Schema
// =============================================================================

export interface CitationDetail {
  id: string;
  tag: string;
  title: string;
  source: string;
  timestamp: string;
  summary: string;
  verification: string;
  sourceType: 'news' | 'graph' | 'erp' | 'contract';
}

export const CITATION_REGISTRY: Record<string, CitationDetail> = {
  'REUTERS-TW-9921': {
    id: 'REUTERS-TW-9921',
    tag: 'REUTERS-TW-9921',
    title: 'Taiwan Fire Agency Incident Dispatch #FA-2026-992',
    source: 'Taiwan National Fire Agency & Commercial Intelligence Feed',
    timestamp: '2026-11-24T08:14:22Z',
    summary:
      'Confirmed electrical transformer fire halted Fab 2 diffusion line at NanoCore Semiconductor in Hsinchu. Suppression completed; cleanroom atmospheric seal breach confirmed. Production freeze estimated at >= 21 calendar days.',
    verification: 'Verified (Triple-Corroborated by Thermal Satellite & Local Authorities)',
    sourceType: 'news',
  },
  'NEPTUNE-GRAPH': {
    id: 'NEPTUNE-GRAPH',
    tag: 'NEPTUNE-GRAPH',
    title: 'Amazon Neptune Multi-Tier Graph Path Traversal',
    source: 'ApexMotion Neptune Graph Service (OpenCypher Query)',
    timestamp: '2026-11-24T08:15:02Z',
    summary:
      'Dependency Path: NanoCore Semiconductor [Tier-2] -> MCU-X91 [Component] -> BetaElectro GmbH [Tier-1] -> BMS-E4 Module -> Munich, Bengaluru, & Pune Plants -> Model-X Performance and Hyper-GT Vehicle Programs.',
    verification: 'Verified (Internal Knowledge Graph Certified - Depth: 3 Tiers)',
    sourceType: 'graph',
  },
  'SAP-INV-001': {
    id: 'SAP-INV-001',
    tag: 'SAP-INV-001',
    title: 'SAP S/4HANA Certified Inventory & Inbound PO Balances',
    source: 'SAP ERP S/4HANA Material Management (MM) Connector',
    timestamp: '2026-11-24T08:15:10Z',
    summary:
      'Material SKU-MCU-4402: Usable On-Hand Physical Stock = 142,000 EA across Munich Hub. 30-Day Rolling Burn Rate = 18,500 EA/day. Open Inbound Purchase Order #PO-88921 Inbound Transit ETA = 9.0 days.',
    verification: 'Verified (Live SAP ERP Certified Balance - ECC/S4 Audit Synced)',
    sourceType: 'erp',
  },
  'MSA-2024-BE §14.2': {
    id: 'MSA-2024-BE §14.2',
    tag: 'MSA-2024-BE §14.2',
    title: 'Master Supply Agreement §14.2 (BetaElectro GmbH)',
    source: 'ApexMotion OpenSearch Contract Index #MSA-2024-BE',
    timestamp: '2026-11-24T08:15:35Z',
    summary:
      'Section 14.2 (Disruption & Force Majeure Exclusions): Force Majeure relief is strictly denied while pre-qualified AML alternate suppliers exist. Section 14.2(c) obligates BetaElectro to absorb 50% of expedited air freight surcharges up to $100,000.',
    verification: 'Verified (Digitized Legal Contract Index - Vector Match: 0.96)',
    sourceType: 'contract',
  },
};

// =============================================================================
// Canonical NanoCore Reference Dossier (FRD FR-DEC-001 / Golden Test Match)
// =============================================================================

export const CANONICAL_NANOCORE_INVESTIGATION: InvestigationDetailResponse = {
  investigation_id: 'inv-nc-2026-091a',
  case_id: 'CASE-2026-091',
  alert_id: 'ALT-NC-001',
  supplier_id: 'SUP-NC-001',
  component_sku: 'SKU-MCU-4402',
  status: 'AWAITING_APPROVAL',
  current_node: 'hitl_gate',
  execution_path: ['triage', 'research', 'contract', 'risk', 'recommendation', 'hitl_gate'],
  risk_metrics: {
    usable_inventory_units: 142000,
    daily_consumption_units: 18500,
    days_of_cover: 7.68,
    inbound_eta_days: 9.0,
    shortage_gap_days: 1.32,
    projected_unit_shortage: 24420,
    total_financial_exposure_usd: 2448105.0,
    operating_halt_hours: 28.3,
    assembly_halt_cost_eur: 85000.0,
    unit_cost_usd: 100.25,
  },
  severity: 'CRITICAL',
  narrative: `1. Verified Disruption Event: At 08:14 UTC, a verified electrical cleanroom fire halted Fab 2 operations at NanoCore Semiconductor in Hsinchu, Taiwan [REUTERS-TW-9921]. Satellite thermal imagery confirms production freeze for at least 21 calendar days.

2. Sub-Tier Dependency Mapping: Traversal of the Amazon Neptune Knowledge Graph confirms NanoCore is the single-source maker of the MCU-X91 32-bit Microcontroller, supplied directly to Tier-1 electronics partner BetaElectro GmbH [NEPTUNE-GRAPH]. BetaElectro integrates MCU-X91 into the BMS-E4 Battery Control Unit assembled at Munich, Bengaluru, and Pune plants for the Model-X Performance and Hyper-GT vehicle programs.

3. Inventory Runway & Shortage Calculation: Live SAP S/4HANA stock at Munich is 142,000 units against an aggregate burn rate of 18,500 units/day across 3 plants [SAP-INV-001]. The Deterministic Engine computes an exact Days of Cover of 7.68 Days. Inbound maritime transit PO #88921 is delayed to 9.0 days, producing an unmitigated 1.32-day stockout gap (24,420 units) starting on Day 8.

4. Commercial & Contractual Recourse: Under Master Service Agreement #MSA-2024-BE §14.2, cleanroom fire does NOT permit unilateral Force Majeure waiver while pre-qualified AML alternate suppliers exist [MSA-2024-BE §14.2]. Furthermore, §14.2(c) obligates BetaElectro to absorb 50% of expedited air freight surcharges up to $100,000.`,
  research_analysis: {
    confidence: 0.94,
    incident_name: 'NanoCore Semiconductor Fab 2 Cleanroom Electrical Fire',
    location: 'Hsinchu Science Park, Taiwan (Fab 2)',
    corroborating_sources: [
      'Taiwan National Fire Agency (NFA-TW)',
      'NOAA Satellite Thermal Imagery #SAT-9921',
      'MarineTraffic AIS Carrier Telemetry',
    ],
    blast_radius: {
      tier_depth: 3,
      root_supplier: 'NanoCore Microelectronics Ltd (Tier-2)',
      direct_tier1_supplier: 'BetaElectro GmbH (Tier-1)',
      impacted_components: ['MCU-X91 32-bit Microcontroller', 'BMS-E4 Battery Control Unit'],
      impacted_plants: ['Munich Assembly Plant (DE)', 'Bengaluru EV Center (IN)', 'Pune Battery Facility (IN)'],
      impacted_programs: ['Model-X Performance EV', 'Hyper-GT Dual-Motor'],
    },
  },
  contract_analysis: {
    contract_id: 'MSA-2024-BE',
    supplier_name: 'BetaElectro GmbH',
    governing_law: 'German Commercial Code (HGB) / Munich Jurisdiction',
    clauses: [
      {
        section: '14.2.1',
        title: 'Force Majeure Relief Exclusion',
        status: 'DENIED',
        summary: 'Force Majeure claims are void when pre-qualified alternate suppliers on the Approved Manufacturer List (AML) remain functional.',
      },
      {
        section: '14.2.3',
        title: 'Expedited Air Freight Surcharge Cost-Sharing',
        status: '50/50 SHARING',
        summary: 'BetaElectro must absorb 50% of expedited premium air freight costs up to a cumulative cap of $100,000 USD.',
      },
      {
        section: '18.4',
        title: 'Delivery Delay SLA Penalty',
        status: 'PENALTY ACTIVE',
        summary: '+3.0% SLA penalty per calendar day beyond dock receipt date, capped at 25% of total Purchase Order value.',
      },
    ],
  },
  recommendations: [
    {
      scenario_id: 'SCEN-001',
      scenario_type: 'LOGISTICS_EXPEDITE',
      title: 'Dedicated Air Charter Cargo Flight (80,000 units)',
      estimated_cost_usd: 180000.0,
      lead_time_days: 3.5,
      net_benefit_usd: 2268105.0,
      spend_tier: 'PROC_DIRECTOR',
      requires_hitl: true,
      description:
        'Convert maritime container shipment to dedicated charter Boeing 777F flight directly into Munich (MUC). Recovers 5.5 days of transit, eliminating all 28.3 hours of plant downtime penalties (€2.4M saved).',
    },
    {
      scenario_id: 'SCEN-002',
      scenario_type: 'SECONDARY_SOURCE',
      title: 'Activate MicroChip Global (Approved AML Secondary)',
      estimated_cost_usd: 240000.0,
      lead_time_days: 6.0,
      net_benefit_usd: 1850000.0,
      spend_tier: 'DUAL_VP',
      requires_hitl: true,
      description:
        'Issue emergency spot purchase order under MSA §14.2 to MicroChip Global Singapore fab. Fulfills 50,000 units in 6.0 days, curtailing stockout gap to 0.4 days.',
    },
    {
      scenario_id: 'SCEN-003',
      scenario_type: 'LINE_REBALANCE',
      title: 'Throttle Standard Line by 30% (Prioritize Model-X)',
      estimated_cost_usd: 75000.0,
      lead_time_days: 1.0,
      net_benefit_usd: 950000.0,
      spend_tier: 'CATEGORY_MGR',
      requires_hitl: true,
      description:
        'Shift remaining MCU-X91 inventory allocation exclusively to high-margin Model-X production lines, reducing standard EV assembly by 30% for 4 days.',
    },
  ],
  recommended_action_id: 'SCEN-001',
  requires_hitl: true,
  governing_spend_tier: 'PROC_DIRECTOR',
  errors: [],
  started_at: '2026-11-24T08:14:22Z',
  completed_at: '2026-11-24T08:15:44Z',
  duration_ms: 82400,
  tokens_used: 4820,
  cost_usd: '0.048',
};

// =============================================================================
// Store Interface
// =============================================================================

export interface InvestigationState {
  // Current Active Record
  activeInvestigationId: string | null;
  currentInvestigation: InvestigationDetailResponse | null;

  // Lifecycle Flags
  isTriggering: boolean;
  isPolling: boolean;
  isDegradedMode: boolean; // Simulates circuit breaker LLM fallback (FRD FR-DEC-001 Alt Flow)
  elapsedSeconds: number;
  error: string | null;

  // Interactive Modals
  isTriggerModalOpen: boolean;
  selectedCitation: CitationDetail | null;

  // Actions
  triggerInvestigation: (req: InvestigationStartRequest) => Promise<InvestigationStartResponse>;
  fetchInvestigation: (investigationId: string) => Promise<InvestigationDetailResponse>;
  startPolling: (investigationId: string) => void;
  stopPolling: () => void;
  loadCanonicalScenario: () => void;
  setIsTriggerModalOpen: (open: boolean) => void;
  setSelectedCitation: (citation: CitationDetail | null) => void;
  setDegradedMode: (degraded: boolean) => void;
  reset: () => void;
}

// Module-level polling interval reference
let pollIntervalId: ReturnType<typeof setInterval> | null = null;
let timerIntervalId: ReturnType<typeof setInterval> | null = null;

export const useInvestigationStore = create<InvestigationState>((set, get) => ({
  activeInvestigationId: 'inv-nc-2026-091a',
  currentInvestigation: CANONICAL_NANOCORE_INVESTIGATION,
  isTriggering: false,
  isPolling: false,
  isDegradedMode: false,
  elapsedSeconds: 82,
  error: null,
  isTriggerModalOpen: false,
  selectedCitation: null,

  triggerInvestigation: async (req: InvestigationStartRequest): Promise<InvestigationStartResponse> => {
    set({ isTriggering: true, error: null });
    try {
      const response = await investigationApi.startInvestigation(req);
      set({
        activeInvestigationId: response.investigation_id,
        isTriggering: false,
        elapsedSeconds: 0,
      });

      // Automatically initiate polling loop for the new investigation
      get().startPolling(response.investigation_id);
      return response;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to launch investigation pipeline';
      set({ isTriggering: false, error: msg });
      throw err;
    }
  },

  fetchInvestigation: async (investigationId: string): Promise<InvestigationDetailResponse> => {
    try {
      const response = await investigationApi.getInvestigation(investigationId);
      set({
        currentInvestigation: response,
        activeInvestigationId: investigationId,
        error: null,
      });

      // Check terminal states to auto-terminate polling
      const terminalStatuses = ['COMPLETED', 'AWAITING_APPROVAL', 'DISMISSED', 'FAILED'];
      if (terminalStatuses.includes(response.status)) {
        get().stopPolling();
      }

      return response;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error fetching investigation details';
      // If backend mock is offline or record not found, retain existing state with warning
      set({ error: msg });
      throw err;
    }
  },

  startPolling: (investigationId: string) => {
    get().stopPolling();

    set({
      isPolling: true,
      activeInvestigationId: investigationId,
      elapsedSeconds: 0,
      error: null,
    });

    // 1-second UI stopwatch ticker
    timerIntervalId = setInterval(() => {
      set((state) => ({ elapsedSeconds: state.elapsedSeconds + 1 }));
    }, 1000);

    // Initial fetch immediately
    void get().fetchInvestigation(investigationId).catch(() => {
      // Handled in fetchInvestigation
    });

    // 2.5s asynchronous polling interval
    pollIntervalId = setInterval(() => {
      const { elapsedSeconds, isPolling } = get();
      if (!isPolling) {
        get().stopPolling();
        return;
      }

      // Circuit breaker fallback check if exceeds 90s SLA
      if (elapsedSeconds >= 90) {
        set({ isDegradedMode: true });
      }

      void get().fetchInvestigation(investigationId).catch(() => {
        // Handled in fetchInvestigation
      });
    }, 2500);
  },

  stopPolling: () => {
    if (pollIntervalId !== null) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    if (timerIntervalId !== null) {
      clearInterval(timerIntervalId);
      timerIntervalId = null;
    }
    set({ isPolling: false });
  },

  loadCanonicalScenario: () => {
    get().stopPolling();
    set({
      activeInvestigationId: 'inv-nc-2026-091a',
      currentInvestigation: CANONICAL_NANOCORE_INVESTIGATION,
      isPolling: false,
      isDegradedMode: false,
      elapsedSeconds: 82,
      error: null,
    });
  },

  setIsTriggerModalOpen: (open: boolean) => set({ isTriggerModalOpen: open }),
  setSelectedCitation: (citation: CitationDetail | null) => set({ selectedCitation: citation }),
  setDegradedMode: (degraded: boolean) => set({ isDegradedMode: degraded }),

  reset: () => {
    get().stopPolling();
    set({
      activeInvestigationId: null,
      currentInvestigation: null,
      isTriggering: false,
      isPolling: false,
      isDegradedMode: false,
      elapsedSeconds: 0,
      error: null,
      isTriggerModalOpen: false,
      selectedCitation: null,
    });
  },
}));
