// ==============================================================================
// ApexMotion Supplier Risk Intelligence Platform — Neptune OpenCypher Seed Schema
// Standard Graph Topology for Multi-Tier Automotive Supply Network
// Reference: CLAUDE.md Section 8.2 & FRD Section 5.2
// Golden Reference: NanoCore Semiconductor Disruption Scenario (SUP-NC-882)
// ==============================================================================

// ------------------------------------------------------------------------------
// 1. Core Supplier Nodes (Tier 1, Tier 2, Tier 3)
// ------------------------------------------------------------------------------
MERGE (nc:Supplier {id: 'SUP-NC-882'})
SET nc.name = 'NanoCore Semiconductor',
    nc.tier = 2,
    nc.country = 'TW',
    nc.risk_score = 0.88,
    nc.aml_status = 'CLEAR',
    nc.last_updated = '2026-11-20T10:00:00Z';

MERGE (be:Supplier {id: 'SUP-BE-101'})
SET be.name = 'BetaElectro AG',
    be.tier = 1,
    be.country = 'DE',
    be.risk_score = 0.22,
    be.aml_status = 'CLEAR',
    be.last_updated = '2026-11-20T10:00:00Z';

MERGE (vl:Supplier {id: 'SUP-VL-501'})
SET vl.name = 'Volta Lithium Resources',
    vl.tier = 3,
    vl.country = 'AU',
    vl.risk_score = 0.35,
    vl.aml_status = 'CLEAR',
    vl.last_updated = '2026-11-20T10:00:00Z';

MERGE (mc:Supplier {id: 'SUP-MC-002'})
SET mc.name = 'MicroChip Global Semiconductors',
    mc.tier = 2,
    mc.country = 'US',
    mc.risk_score = 0.25,
    mc.aml_status = 'CLEAR',
    mc.last_updated = '2026-11-20T10:00:00Z';

MERGE (sil:Supplier {id: 'SUP-SIL-901'})
SET sil.name = 'Siltronic Silicon Wafers AG',
    sil.tier = 3,
    sil.country = 'DE',
    sil.risk_score = 0.15,
    sil.aml_status = 'CLEAR',
    sil.last_updated = '2026-11-20T10:00:00Z';

// ------------------------------------------------------------------------------
// 2. Component Nodes (Bill of Materials Items)
// ------------------------------------------------------------------------------
MERGE (mcu:Component {id: 'CMP-MCU-X91'})
SET mcu.mpn = 'MCU-X91',
    mcu.sku = 'SKU-77291',
    mcu.description = '32-Bit Automotive Grade Microcontroller Unit',
    mcu.criticality = 'CRITICAL',
    mcu.days_of_cover = 7.68,
    mcu.daily_consumption_rate = 18500.0;

MERGE (pmic:Component {id: 'CMP-PMIC-440'})
SET pmic.mpn = 'PMIC-440',
    pmic.sku = 'SKU-88120',
    pmic.description = 'High-Efficiency Power Management Integrated Circuit',
    pmic.criticality = 'HIGH',
    pmic.days_of_cover = 14.5,
    pmic.daily_consumption_rate = 9200.0;

// ------------------------------------------------------------------------------
// 3. Assembly Nodes (Sub-Systems)
// ------------------------------------------------------------------------------
MERGE (ecu:Assembly {id: 'ASM-BECU-04'})
SET ecu.assembly_id = 'ASM-BECU-04',
    ecu.bom_rev = '4.2',
    ecu.name = 'High-Voltage Battery Electronic Control Unit (ECU)';

// ------------------------------------------------------------------------------
// 4. Plant Nodes (Manufacturing & Assembly Facilities)
// ------------------------------------------------------------------------------
MERGE (muc:Plant {id: 'PLT-MUC-01'})
SET muc.plant_id = 'PLT-MUC-01',
    muc.name = 'Munich Assembly Hub',
    muc.location = 'Munich',
    muc.country = 'DE',
    muc.region = 'EMEA',
    muc.hourly_downtime_rate_usd = 92000.0,
    muc.rate_eur = 85000.0,
    muc.capacity = 500;

MERGE (blr:Plant {id: 'PLT-BLR-02'})
SET blr.plant_id = 'PLT-BLR-02',
    blr.name = 'Bengaluru Electronics Facility',
    blr.location = 'Bengaluru',
    blr.country = 'IN',
    blr.region = 'APAC',
    blr.hourly_downtime_rate_usd = 28000.0,
    blr.rate_eur = 25000.0,
    blr.capacity = 350;

// ------------------------------------------------------------------------------
// 5. Program Nodes (Vehicle Model Allocations)
// ------------------------------------------------------------------------------
MERGE (hypergt:Program {id: 'PRG-HGT-2026'})
SET hypergt.program_id = 'PRG-HGT-2026',
    hypergt.model = 'Apex Hyper-GT',
    hypergt.daily_target_units = 250,
    hypergt.margin = 14500.0,
    hypergt.margin_per_unit_usd = 14500.0;

// ------------------------------------------------------------------------------
// 6. Contract Nodes (Procurement Agreements)
// ------------------------------------------------------------------------------
MERGE (ctr_nc:Contract {id: 'CTR-NC-2024-01'})
SET ctr_nc.supplier_id = 'SUP-NC-882',
    ctr_nc.value_usd = 2448105.00,
    ctr_nc.expiry_date = '2026-12-31',
    ctr_nc.payment_terms = 'NET_60';

MERGE (ctr_be:Contract {id: 'CTR-BE-2023-09'})
SET ctr_be.supplier_id = 'SUP-BE-101',
    ctr_be.value_usd = 18500000.00,
    ctr_be.expiry_date = '2027-06-30',
    ctr_be.payment_terms = 'NET_45';

// ------------------------------------------------------------------------------
// 7. News & Geopolitical Risk External Signals
// ------------------------------------------------------------------------------
MERGE (news:NewsEvent {id: 'EVT-NEWS-2026-081'})
SET news.headline = 'Cleanroom facility fire reported at Hsinchu Science Park, wafer testing halted',
    news.sentiment = -0.85,
    news.source = 'Reuters',
    news.published_at = '2026-11-20T08:15:00Z';

MERGE (geo:GeopoliticalRisk {id: 'RISK-GEO-TW-01'})
SET geo.region = 'East Asia / Taiwan Strait',
    geo.risk_type = 'EXPORT_RESTRICTION_LOGISTICS',
    geo.severity = 'HIGH',
    geo.description = 'Bilateral export controls and maritime shipping lane congestion in the Taiwan Strait corridor.';

MERGE (geo2:GeopoliticalRisk {id: 'RISK-GEO-TW-02'})
SET geo2.region = 'Northern Taiwan / Hsinchu',
    geo2.risk_type = 'SEISMIC_AND_POWER_VULNERABILITY',
    geo2.severity = 'HIGH',
    geo2.description = 'Subduction fault seismic activity and cleanroom power grid concentration across Hsinchu Science Park.';

MERGE (geo3:GeopoliticalRisk {id: 'RISK-GEO-TW-03'})
SET geo3.region = 'Taiwan Strait / South China Sea',
    geo3.risk_type = 'MARITIME_CHOKEPOINT_BLOCKADE',
    geo3.severity = 'CRITICAL',
    geo3.description = 'Airspace restrictions and naval blockade exercises threatening primary container shipping routes.';

// ------------------------------------------------------------------------------
// 8. Graph Edges & Supply Chain Relationships
// ------------------------------------------------------------------------------

// Supplier to Component Part Supply
MATCH (nc:Supplier {id: 'SUP-NC-882'}), (mcu:Component {id: 'CMP-MCU-X91'})
MERGE (nc)-[r:SUPPLIES]->(mcu)
SET r.contract_id = 'CTR-NC-2024-01';

MATCH (nc:Supplier {id: 'SUP-NC-882'}), (mcu:Component {id: 'CMP-MCU-X91'})
MERGE (nc)-[r:SUPPLIES_PART]->(mcu)
SET r.lead_time_days = 45, r.is_single_source = true;

MATCH (vl:Supplier {id: 'SUP-VL-501'}), (pmic:Component {id: 'CMP-PMIC-440'})
MERGE (vl)-[r:SUPPLIES_PART]->(pmic)
SET r.lead_time_days = 60, r.is_single_source = false;

MATCH (mc:Supplier {id: 'SUP-MC-002'}), (mcu:Component {id: 'CMP-MCU-X91'})
MERGE (mc)-[r:SUPPLIES_PART]->(mcu)
SET r.lead_time_days = 28, r.is_single_source = false;

// Component to Plant Direct Consumption
MATCH (mcu:Component {id: 'CMP-MCU-X91'}), (muc:Plant {id: 'PLT-MUC-01'})
MERGE (mcu)-[:USED_BY]->(muc);

MATCH (mcu:Component {id: 'CMP-MCU-X91'}), (blr:Plant {id: 'PLT-BLR-02'})
MERGE (mcu)-[:USED_BY]->(blr);

MATCH (pmic:Component {id: 'CMP-PMIC-440'}), (blr:Plant {id: 'PLT-BLR-02'})
MERGE (pmic)-[:USED_BY]->(blr);

// Tier Chain: NanoCore (Tier 2) is sub-tier supplier to BetaElectro (Tier 1)
MATCH (nc:Supplier {id: 'SUP-NC-882'}), (be:Supplier {id: 'SUP-BE-101'})
MERGE (nc)-[:TIER_1_OF]->(be);

// Tier Chain: Siltronic Wafers (Tier 3) supplies NanoCore (Tier 2)
MATCH (sil:Supplier {id: 'SUP-SIL-901'}), (nc:Supplier {id: 'SUP-NC-882'})
MERGE (sil)-[:TIER_1_OF]->(nc);

// Tier Chain: MicroChip (Tier 2) supplies BetaElectro (Tier 1)
MATCH (mc:Supplier {id: 'SUP-MC-002'}), (be:Supplier {id: 'SUP-BE-101'})
MERGE (mc)-[:TIER_1_OF]->(be);

// Component to Assembly BOM Structure
MATCH (mcu:Component {id: 'CMP-MCU-X91'}), (ecu:Assembly {id: 'ASM-BECU-04'})
MERGE (mcu)-[r:PART_OF_BOM]->(ecu)
SET r.quantity_per_assembly = 2;

// Assembly to Final Manufacturing Plant
MATCH (ecu:Assembly {id: 'ASM-BECU-04'}), (muc:Plant {id: 'PLT-MUC-01'})
MERGE (ecu)-[r:ASSEMBLED_AT]->(muc)
SET r.primary_line = 'Line-B';

// Plant Capacity Allocation to Vehicle Program
MATCH (muc:Plant {id: 'PLT-MUC-01'}), (hypergt:Program {id: 'PRG-HGT-2026'})
MERGE (muc)-[r:ALLOCATED_TO]->(hypergt)
SET r.daily_build_quota = 250;

// Contractual Governance
MATCH (nc:Supplier {id: 'SUP-NC-882'}), (ctr_nc:Contract {id: 'CTR-NC-2024-01'})
MERGE (nc)-[:BOUND_BY]->(ctr_nc);

MATCH (be:Supplier {id: 'SUP-BE-101'}), (ctr_be:Contract {id: 'CTR-BE-2023-09'})
MERGE (be)-[:BOUND_BY]->(ctr_be);

// External Incident Signals
MATCH (news:NewsEvent {id: 'EVT-NEWS-2026-081'}), (nc:Supplier {id: 'SUP-NC-882'})
MERGE (news)-[:AFFECTS]->(nc);

MATCH (geo:GeopoliticalRisk {id: 'RISK-GEO-TW-01'}), (nc:Supplier {id: 'SUP-NC-882'})
MERGE (geo)-[:THREATENS]->(nc);

MATCH (geo2:GeopoliticalRisk {id: 'RISK-GEO-TW-02'}), (nc:Supplier {id: 'SUP-NC-882'})
MERGE (geo2)-[:THREATENS]->(nc);

MATCH (geo3:GeopoliticalRisk {id: 'RISK-GEO-TW-03'}), (nc:Supplier {id: 'SUP-NC-882'})
MERGE (geo3)-[:THREATENS]->(nc);
