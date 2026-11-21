// ==============================================================================
// ApexMotion Supplier Risk Intelligence Platform — Neptune OpenCypher Seed Schema
// Standard Graph Topology for Multi-Tier Automotive Supply Network
// Reference: CLAUDE.md Section 8.2 & FRD Section 5.2
// Golden Reference: NanoCore Semiconductor Disruption Scenario (SUP-NC-882)
// ==============================================================================

// ------------------------------------------------------------------------------
// 1. Core Supplier Nodes (Tier 1, Tier 2, Tier 3)
// ------------------------------------------------------------------------------
CREATE (nc:Supplier {
    id: 'SUP-NC-882',
    name: 'NanoCore Semiconductor',
    tier: 2,
    country: 'TW',
    risk_score: 0.88,
    aml_status: 'CLEAR',
    last_updated: '2026-11-20T10:00:00Z'
});

CREATE (be:Supplier {
    id: 'SUP-BE-101',
    name: 'BetaElectro AG',
    tier: 1,
    country: 'DE',
    risk_score: 0.22,
    aml_status: 'CLEAR',
    last_updated: '2026-11-20T10:00:00Z'
});

CREATE (vl:Supplier {
    id: 'SUP-VL-501',
    name: 'Volta Lithium Resources',
    tier: 3,
    country: 'AU',
    risk_score: 0.35,
    aml_status: 'CLEAR',
    last_updated: '2026-11-20T10:00:00Z'
});

// ------------------------------------------------------------------------------
// 2. Component Nodes (Bill of Materials Items)
// ------------------------------------------------------------------------------
CREATE (mcu:Component {
    id: 'CMP-MCU-X91',
    mpn: 'MCU-X91',
    sku: 'SKU-77291',
    description: '32-Bit Automotive Grade Microcontroller Unit',
    criticality: 'CRITICAL',
    days_of_cover: 7.68,
    daily_consumption_rate: 18500.0
});

CREATE (pmic:Component {
    id: 'CMP-PMIC-440',
    mpn: 'PMIC-440',
    sku: 'SKU-88120',
    description: 'High-Efficiency Power Management Integrated Circuit',
    criticality: 'HIGH',
    days_of_cover: 14.5,
    daily_consumption_rate: 9200.0
});

// ------------------------------------------------------------------------------
// 3. Assembly Nodes (Sub-Systems)
// ------------------------------------------------------------------------------
CREATE (ecu:Assembly {
    id: 'ASM-BECU-04',
    assembly_id: 'ASM-BECU-04',
    bom_rev: '4.2',
    name: 'High-Voltage Battery Electronic Control Unit (ECU)'
});

// ------------------------------------------------------------------------------
// 4. Plant Nodes (Manufacturing & Assembly Facilities)
// ------------------------------------------------------------------------------
CREATE (muc:Plant {
    id: 'PLT-MUC-01',
    plant_id: 'PLT-MUC-01',
    name: 'Munich Assembly Hub',
    location: 'Munich',
    country: 'DE',
    region: 'EMEA',
    hourly_downtime_rate_usd: 92000.0,
    rate_eur: 85000.0,
    capacity: 500
});

CREATE (blr:Plant {
    id: 'PLT-BLR-02',
    plant_id: 'PLT-BLR-02',
    name: 'Bengaluru Electronics Facility',
    location: 'Bengaluru',
    country: 'IN',
    region: 'APAC',
    hourly_downtime_rate_usd: 28000.0,
    capacity: 350
});

// ------------------------------------------------------------------------------
// 5. Program Nodes (Vehicle Model Allocations)
// ------------------------------------------------------------------------------
CREATE (hypergt:Program {
    id: 'PRG-HGT-2026',
    program_id: 'PRG-HGT-2026',
    model: 'Apex Hyper-GT',
    daily_target_units: 250,
    margin: 14500.0,
    margin_per_unit_usd: 14500.0
});

// ------------------------------------------------------------------------------
// 6. Contract Nodes (Procurement Agreements)
// ------------------------------------------------------------------------------
CREATE (ctr_nc:Contract {
    id: 'CTR-NC-2024-01',
    supplier_id: 'SUP-NC-882',
    value_usd: 2448105.00,
    expiry_date: '2026-12-31',
    payment_terms: 'NET_60'
});

CREATE (ctr_be:Contract {
    id: 'CTR-BE-2023-09',
    supplier_id: 'SUP-BE-101',
    value_usd: 18500000.00,
    expiry_date: '2027-06-30',
    payment_terms: 'NET_45'
});

// ------------------------------------------------------------------------------
// 7. News & Geopolitical Risk External Signals
// ------------------------------------------------------------------------------
CREATE (news:NewsEvent {
    id: 'EVT-NEWS-2026-081',
    headline: 'Cleanroom facility fire reported at Hsinchu Science Park, wafer testing halted',
    sentiment: -0.85,
    source: 'Reuters',
    published_at: '2026-11-20T08:15:00Z'
});

CREATE (geo:GeopoliticalRisk {
    id: 'RISK-GEO-TW-01',
    region: 'East Asia',
    risk_type: 'EXPORT_RESTRICTION_LOGISTICS',
    severity: 'HIGH'
});

// ------------------------------------------------------------------------------
// 8. Graph Edges & Supply Chain Relationships
// ------------------------------------------------------------------------------

// Supplier to Component Part Supply
CREATE (nc)-[:SUPPLIES {contract_id: 'CTR-NC-2024-01'}]->(mcu);
CREATE (nc)-[:SUPPLIES_PART {lead_time_days: 45, is_single_source: true}]->(mcu);
CREATE (vl)-[:SUPPLIES_PART {lead_time_days: 60, is_single_source: false}]->(pmic);

// Component to Plant Direct Consumption
CREATE (mcu)-[:USED_BY]->(muc);
CREATE (pmic)-[:USED_BY]->(blr);

// Tier Chain: NanoCore (Tier 2) is sub-tier supplier to BetaElectro (Tier 1)
CREATE (nc)-[:TIER_1_OF]->(be);

// Component to Assembly BOM Structure
CREATE (mcu)-[:PART_OF_BOM {quantity_per_assembly: 2}]->(ecu);

// Assembly to Final Manufacturing Plant
CREATE (ecu)-[:ASSEMBLED_AT {primary_line: 'Line-B'}]->(muc);

// Plant Capacity Allocation to Vehicle Program
CREATE (muc)-[:ALLOCATED_TO {daily_build_quota: 250}]->(hypergt);

// Contractual Governance
CREATE (nc)-[:BOUND_BY]->(ctr_nc);
CREATE (be)-[:BOUND_BY]->(ctr_be);

// External Incident Signals
CREATE (news)-[:AFFECTS]->(nc);
CREATE (geo)-[:THREATENS]->(nc);
