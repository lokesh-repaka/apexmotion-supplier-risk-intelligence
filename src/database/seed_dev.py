"""Development database seeding script for ApexMotion Platform (P13-1).

Seeds:
- 50+ Tier-1 suppliers across 10 countries (DE, JP, US, KR, TW, CN, MX, IN, VN, GB),
  plus key sub-tier suppliers (NanoCore, MicroChip, Volta Lithium, BetaElectro).
- 20 automotive manufacturing and assembly plants.
- 200 distinct component SKUs across 10 automotive categories with realistic inventory snapshots.
- The canonical NanoCore golden scenario (CLAUDE.md Section 14, BR-RULE-001):
  - Supplier: NanoCore Semiconductor Ltd (SUP-NC-001 / SUP-NC-882, TW, Tier-2, risk 0.880)
  - Component: SKU-MCU-4402 at Munich Assembly Hub (PLT-MUC-01)
  - Current stock: 142,000 units
  - Daily consumption: 18,500 units/day
  - Unit cost: $100.25
  - Replenishment ETA: 9.00 days
  - Days of cover: 7.68 days
  - Shortage volume: 24,420 units
  - Financial exposure: $2,448,105.00
  - Risk severity: CRITICAL
  - Status: OPEN

Usage:
    python -m src.database.seed_dev [--clear] [--dry-run] [--verify]
"""

import argparse
import asyncio
import sys
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.database.models import (
    AuditLog,
    InventorySnapshot,
    RiskAlert,
    Supplier,
)
from src.database.session import get_async_session_factory

logger = get_logger("apexmotion.database.seed_dev")


# ==============================================================================
# 1. 20 Automotive Manufacturing & Assembly Plants
# ==============================================================================

PLANTS_CATALOG: list[dict[str, Any]] = [
    {
        "plant_id": "PLT-MUC-01",
        "name": "Munich Assembly Hub",
        "location": "Munich",
        "country": "DE",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("92000.00"),
        "hourly_downtime_rate_eur": Decimal("85000.00"),
        "capacity_vehicles_per_day": 500,
    },
    {
        "plant_id": "PLT-BLR-02",
        "name": "Bengaluru Electronics Facility",
        "location": "Bengaluru",
        "country": "IN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("28000.00"),
        "hourly_downtime_rate_eur": Decimal("25000.00"),
        "capacity_vehicles_per_day": 350,
    },
    {
        "plant_id": "PLT-PUN-03",
        "name": "Pune Powertrain Plant",
        "location": "Pune",
        "country": "IN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("32000.00"),
        "hourly_downtime_rate_eur": Decimal("29000.00"),
        "capacity_vehicles_per_day": 400,
    },
    {
        "plant_id": "PLT-STU-01",
        "name": "Stuttgart Stamping Facility",
        "location": "Stuttgart",
        "country": "DE",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("88000.00"),
        "hourly_downtime_rate_eur": Decimal("81000.00"),
        "capacity_vehicles_per_day": 450,
    },
    {
        "plant_id": "PLT-LEI-01",
        "name": "Leipzig EV Innovation Center",
        "location": "Leipzig",
        "country": "DE",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("95000.00"),
        "hourly_downtime_rate_eur": Decimal("88000.00"),
        "capacity_vehicles_per_day": 600,
    },
    {
        "plant_id": "PLT-GRA-01",
        "name": "Graz Battery Pack Facility",
        "location": "Graz",
        "country": "AT",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("75000.00"),
        "hourly_downtime_rate_eur": Decimal("70000.00"),
        "capacity_vehicles_per_day": 300,
    },
    {
        "plant_id": "PLT-SLP-01",
        "name": "San Luis Potosi Vehicle Assembly",
        "location": "San Luis Potosi",
        "country": "MX",
        "region": "AMER",
        "hourly_downtime_rate_usd": Decimal("55000.00"),
        "hourly_downtime_rate_eur": Decimal("51000.00"),
        "capacity_vehicles_per_day": 550,
    },
    {
        "plant_id": "PLT-AUST-01",
        "name": "Austin Gigafactory",
        "location": "Austin",
        "country": "US",
        "region": "AMER",
        "hourly_downtime_rate_usd": Decimal("110000.00"),
        "hourly_downtime_rate_eur": Decimal("102000.00"),
        "capacity_vehicles_per_day": 750,
    },
    {
        "plant_id": "PLT-YOK-01",
        "name": "Yokohama Power & Sensor Hub",
        "location": "Yokohama",
        "country": "JP",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("82000.00"),
        "hourly_downtime_rate_eur": Decimal("76000.00"),
        "capacity_vehicles_per_day": 480,
    },
    {
        "plant_id": "PLT-WOL-01",
        "name": "Wolfsburg Modular Tooling Plant",
        "location": "Wolfsburg",
        "country": "DE",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("89000.00"),
        "hourly_downtime_rate_eur": Decimal("82000.00"),
        "capacity_vehicles_per_day": 520,
    },
    {
        "plant_id": "PLT-OXF-01",
        "name": "Oxford Body & Assembly",
        "location": "Oxford",
        "country": "GB",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("78000.00"),
        "hourly_downtime_rate_eur": Decimal("72000.00"),
        "capacity_vehicles_per_day": 380,
    },
    {
        "plant_id": "PLT-CHE-01",
        "name": "Chennai Chassis & Suspension Plant",
        "location": "Chennai",
        "country": "IN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("30000.00"),
        "hourly_downtime_rate_eur": Decimal("27000.00"),
        "capacity_vehicles_per_day": 420,
    },
    {
        "plant_id": "PLT-HYD-01",
        "name": "Hyderabad Semiconductor Integration",
        "location": "Hyderabad",
        "country": "IN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("35000.00"),
        "hourly_downtime_rate_eur": Decimal("32000.00"),
        "capacity_vehicles_per_day": 280,
    },
    {
        "plant_id": "PLT-BKK-01",
        "name": "Bangkok High-Voltage Harness Plant",
        "location": "Bangkok",
        "country": "TH",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("38000.00"),
        "hourly_downtime_rate_eur": Decimal("35000.00"),
        "capacity_vehicles_per_day": 360,
    },
    {
        "plant_id": "PLT-HAI-01",
        "name": "Haiphong Optics & Sensor Fab",
        "location": "Haiphong",
        "country": "VN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("34000.00"),
        "hourly_downtime_rate_eur": Decimal("31000.00"),
        "capacity_vehicles_per_day": 310,
    },
    {
        "plant_id": "PLT-SZX-01",
        "name": "Shenzhen Power Electronics Facility",
        "location": "Shenzhen",
        "country": "CN",
        "region": "APAC",
        "hourly_downtime_rate_usd": Decimal("62000.00"),
        "hourly_downtime_rate_eur": Decimal("57000.00"),
        "capacity_vehicles_per_day": 650,
    },
    {
        "plant_id": "PLT-GUA-01",
        "name": "Guanajuato Transmission Systems",
        "location": "Guanajuato",
        "country": "MX",
        "region": "AMER",
        "hourly_downtime_rate_usd": Decimal("52000.00"),
        "hourly_downtime_rate_eur": Decimal("48000.00"),
        "capacity_vehicles_per_day": 490,
    },
    {
        "plant_id": "PLT-VAL-01",
        "name": "Valencia Battery Integration",
        "location": "Valencia",
        "country": "ES",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("68000.00"),
        "hourly_downtime_rate_eur": Decimal("63000.00"),
        "capacity_vehicles_per_day": 340,
    },
    {
        "plant_id": "PLT-BRA-01",
        "name": "Bratislava Heavy Electric Chassis",
        "location": "Bratislava",
        "country": "SK",
        "region": "EMEA",
        "hourly_downtime_rate_usd": Decimal("64000.00"),
        "hourly_downtime_rate_eur": Decimal("59000.00"),
        "capacity_vehicles_per_day": 410,
    },
    {
        "plant_id": "PLT-DET-01",
        "name": "Detroit Advanced Powertrain",
        "location": "Detroit",
        "country": "US",
        "region": "AMER",
        "hourly_downtime_rate_usd": Decimal("105000.00"),
        "hourly_downtime_rate_eur": Decimal("97000.00"),
        "capacity_vehicles_per_day": 620,
    },
]


def get_plants_catalog() -> list[dict[str, Any]]:
    """Return immutable list of 20 automotive plant definitions."""
    return [dict(p) for p in PLANTS_CATALOG]


# ==============================================================================
# 2. 50+ Tier-1 Suppliers Across 10 Countries + Sub-Tier Suppliers
# ==============================================================================

RAW_SUPPLIERS_CATALOG: list[dict[str, Any]] = [
    # --- Germany (DE): 6 Tier-1 ---
    {
        "neptune_node_id": "SUP-BOSCH-01",
        "name": "Bosch Mobility Solutions GmbH",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.180"),
    },
    {
        "neptune_node_id": "SUP-CONTI-02",
        "name": "Continental Automotive AG",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.240"),
    },
    {
        "neptune_node_id": "SUP-ZF-03",
        "name": "ZF Friedrichshafen AG",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.210"),
    },
    {
        "neptune_node_id": "SUP-SCHAEF-04",
        "name": "Schaeffler Technologies AG",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.190"),
    },
    {
        "neptune_node_id": "SUP-MAHLE-05",
        "name": "Mahle International GmbH",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.270"),
    },
    {
        "neptune_node_id": "SUP-HELLA-06",
        "name": "Hella Automotive Lighting GmbH",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.220"),
    },
    # --- Japan (JP): 6 Tier-1 ---
    {
        "neptune_node_id": "SUP-DENSO-07",
        "name": "Denso Corporation",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.150"),
    },
    {
        "neptune_node_id": "SUP-AISIN-08",
        "name": "Aisin Corporation",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.200"),
    },
    {
        "neptune_node_id": "SUP-SUMI-09",
        "name": "Sumitomo Electric Industries",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.230"),
    },
    {
        "neptune_node_id": "SUP-YAZAKI-10",
        "name": "Yazaki Automotive Systems",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.190"),
    },
    {
        "neptune_node_id": "SUP-HITACHI-11",
        "name": "Hitachi Astemo Ltd",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.210"),
    },
    {
        "neptune_node_id": "SUP-STANLEY-12",
        "name": "Stanley Electric Co Ltd",
        "country_code": "JP",
        "tier": 1,
        "risk_score": Decimal("0.250"),
    },
    # --- United States (US): 6 Tier-1 ---
    {
        "neptune_node_id": "SUP-MAGNA-13",
        "name": "Magna International Powertrain",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.170"),
    },
    {
        "neptune_node_id": "SUP-LEAR-14",
        "name": "Lear Corporation Seating & E-Systems",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.260"),
    },
    {
        "neptune_node_id": "SUP-BORG-15",
        "name": "BorgWarner Drivetrain Inc",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.210"),
    },
    {
        "neptune_node_id": "SUP-DANA-16",
        "name": "Dana Incorporated Motion Systems",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.240"),
    },
    {
        "neptune_node_id": "SUP-APTIV-17",
        "name": "Aptiv Electrical & Autonomous",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.180"),
    },
    {
        "neptune_node_id": "SUP-VISTEON-18",
        "name": "Visteon Cockpit Electronics",
        "country_code": "US",
        "tier": 1,
        "risk_score": Decimal("0.230"),
    },
    # --- South Korea (KR): 5 Tier-1 ---
    {
        "neptune_node_id": "SUP-MOBIS-19",
        "name": "Hyundai Mobis Co Ltd",
        "country_code": "KR",
        "tier": 1,
        "risk_score": Decimal("0.190"),
    },
    {
        "neptune_node_id": "SUP-MANDO-20",
        "name": "HL Mando Steering & Braking",
        "country_code": "KR",
        "tier": 1,
        "risk_score": Decimal("0.220"),
    },
    {
        "neptune_node_id": "SUP-HANON-21",
        "name": "Hanon Systems Thermal Management",
        "country_code": "KR",
        "tier": 1,
        "risk_score": Decimal("0.250"),
    },
    {
        "neptune_node_id": "SUP-SL-22",
        "name": "SL Corporation Lighting & Electronics",
        "country_code": "KR",
        "tier": 1,
        "risk_score": Decimal("0.280"),
    },
    {
        "neptune_node_id": "SUP-TRANSYS-23",
        "name": "Hyundai Transys Driveline",
        "country_code": "KR",
        "tier": 1,
        "risk_score": Decimal("0.200"),
    },
    # --- Taiwan (TW): 5 Tier-1 ---
    {
        "neptune_node_id": "SUP-FOXCONN-24",
        "name": "Foxconn EV Technology Platform",
        "country_code": "TW",
        "tier": 1,
        "risk_score": Decimal("0.310"),
    },
    {
        "neptune_node_id": "SUP-DELTA-25",
        "name": "Delta Electronics Power Solutions",
        "country_code": "TW",
        "tier": 1,
        "risk_score": Decimal("0.220"),
    },
    {
        "neptune_node_id": "SUP-PEGATRON-26",
        "name": "Pegatron Automotive Modules",
        "country_code": "TW",
        "tier": 1,
        "risk_score": Decimal("0.270"),
    },
    {
        "neptune_node_id": "SUP-QUANTA-27",
        "name": "Quanta Auto Compute Systems",
        "country_code": "TW",
        "tier": 1,
        "risk_score": Decimal("0.290"),
    },
    {
        "neptune_node_id": "SUP-WISTRON-28",
        "name": "Wistron Infocomm Automotive",
        "country_code": "TW",
        "tier": 1,
        "risk_score": Decimal("0.300"),
    },
    # --- China (CN): 6 Tier-1 ---
    {
        "neptune_node_id": "SUP-CATL-29",
        "name": "CATL Battery Solutions Co Ltd",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.330"),
    },
    {
        "neptune_node_id": "SUP-BYD-30",
        "name": "BYD Semiconductor & Electronics",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.350"),
    },
    {
        "neptune_node_id": "SUP-WEICHAI-31",
        "name": "Weichai Power Auto Systems",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.380"),
    },
    {
        "neptune_node_id": "SUP-JOYSON-32",
        "name": "Joyson Electronic Safety Systems",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.290"),
    },
    {
        "neptune_node_id": "SUP-FUYAO-33",
        "name": "Fuyao Glass Automotive Group",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.260"),
    },
    {
        "neptune_node_id": "SUP-CALB-34",
        "name": "CALB Lithium Battery Technology",
        "country_code": "CN",
        "tier": 1,
        "risk_score": Decimal("0.360"),
    },
    # --- Mexico (MX): 5 Tier-1 ---
    {
        "neptune_node_id": "SUP-NEMAK-35",
        "name": "Nemak Aluminum Castings",
        "country_code": "MX",
        "tier": 1,
        "risk_score": Decimal("0.230"),
    },
    {
        "neptune_node_id": "SUP-RASSINI-36",
        "name": "San Luis Rassini Suspension",
        "country_code": "MX",
        "tier": 1,
        "risk_score": Decimal("0.250"),
    },
    {
        "neptune_node_id": "SUP-METALSA-37",
        "name": "Metalsa Structural Components",
        "country_code": "MX",
        "tier": 1,
        "risk_score": Decimal("0.210"),
    },
    {
        "neptune_node_id": "SUP-BROSE-38",
        "name": "Brose Mexico Door Systems",
        "country_code": "MX",
        "tier": 1,
        "risk_score": Decimal("0.240"),
    },
    {
        "neptune_node_id": "SUP-MARTINREA-39",
        "name": "Martinrea International Mexico",
        "country_code": "MX",
        "tier": 1,
        "risk_score": Decimal("0.280"),
    },
    # --- India (IN): 6 Tier-1 ---
    {
        "neptune_node_id": "SUP-TATA-40",
        "name": "Tata AutoComp Systems Ltd",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.220"),
    },
    {
        "neptune_node_id": "SUP-BHARAT-41",
        "name": "Bharat Forge Automotive Ltd",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.240"),
    },
    {
        "neptune_node_id": "SUP-MOTHER-42",
        "name": "Motherson Sumi Wiring Systems",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.190"),
    },
    {
        "neptune_node_id": "SUP-MINDA-43",
        "name": "Uno Minda Acoustic & Switches",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.260"),
    },
    {
        "neptune_node_id": "SUP-SONA-44",
        "name": "Sona Comstar Precision Forging",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.210"),
    },
    {
        "neptune_node_id": "SUP-SUNDRAM-45",
        "name": "Sundram Fasteners Limited",
        "country_code": "IN",
        "tier": 1,
        "risk_score": Decimal("0.230"),
    },
    # --- Vietnam (VN): 4 Tier-1 ---
    {
        "neptune_node_id": "SUP-VINFAST-46",
        "name": "VinFast Component Systems Vietnam",
        "country_code": "VN",
        "tier": 1,
        "risk_score": Decimal("0.340"),
    },
    {
        "neptune_node_id": "SUP-FPT-47",
        "name": "FPT Automotive Software & ECUs",
        "country_code": "VN",
        "tier": 1,
        "risk_score": Decimal("0.280"),
    },
    {
        "neptune_node_id": "SUP-THACO-48",
        "name": "THACO Auto Parts Manufacturing",
        "country_code": "VN",
        "tier": 1,
        "risk_score": Decimal("0.320"),
    },
    {
        "neptune_node_id": "SUP-HANWHA-49",
        "name": "Hanwha Aero Automotive Vietnam",
        "country_code": "VN",
        "tier": 1,
        "risk_score": Decimal("0.270"),
    },
    # --- United Kingdom (GB): 4 Tier-1 ---
    {
        "neptune_node_id": "SUP-GKN-50",
        "name": "GKN Automotive Driveline UK",
        "country_code": "GB",
        "tier": 1,
        "risk_score": Decimal("0.190"),
    },
    {
        "neptune_node_id": "SUP-TIFLUID-51",
        "name": "TI Fluid Systems Automotive",
        "country_code": "GB",
        "tier": 1,
        "risk_score": Decimal("0.230"),
    },
    {
        "neptune_node_id": "SUP-SENIOR-52",
        "name": "Senior Aerospace & Auto Structures",
        "country_code": "GB",
        "tier": 1,
        "risk_score": Decimal("0.250"),
    },
    {
        "neptune_node_id": "SUP-RICARDO-53",
        "name": "Ricardo Engineering Systems",
        "country_code": "GB",
        "tier": 1,
        "risk_score": Decimal("0.180"),
    },
    # --- Key Sub-Tier Suppliers (Tier-2 & Tier-3) ---
    {
        "neptune_node_id": "SUP-NC-001",
        "name": "NanoCore Microelectronics Ltd",
        "country_code": "TW",
        "tier": 2,
        "risk_score": Decimal("0.880"),
    },
    {
        "neptune_node_id": "SUP-NC-882",
        "name": "NanoCore Semiconductor",
        "country_code": "TW",
        "tier": 2,
        "risk_score": Decimal("0.880"),
    },
    {
        "neptune_node_id": "SUP-MC-002",
        "name": "MicroChip Global Semiconductors",
        "country_code": "US",
        "tier": 2,
        "risk_score": Decimal("0.250"),
    },
    {
        "neptune_node_id": "SUP-BE-101",
        "name": "BetaElectro AG",
        "country_code": "DE",
        "tier": 1,
        "risk_score": Decimal("0.220"),
    },
    {
        "neptune_node_id": "SUP-VL-501",
        "name": "Volta Lithium Resources",
        "country_code": "AU",
        "tier": 3,
        "risk_score": Decimal("0.350"),
    },
    {
        "neptune_node_id": "SUP-CO-301",
        "name": "Katanga Cobalt Mining Corp",
        "country_code": "CD",
        "tier": 3,
        "risk_score": Decimal("0.580"),
    },
]


def get_raw_suppliers_catalog() -> list[dict[str, Any]]:
    """Return immutable list of supplier catalog records."""
    return [dict(s) for s in RAW_SUPPLIERS_CATALOG]


# ==============================================================================
# 3. 200 Components Across 10 Automotive Engineering Domains
# ==============================================================================

# 10 categories x 20 SKUs = 200 distinct components
_CATEGORIES_METADATA = [
    (
        "MCU",
        "Microcontrollers & High-Performance Compute",
        Decimal("95.00"),
        Decimal("18000.00"),
        Decimal("130000.00"),
    ),
    (
        "PMIC",
        "Power Management ICs & Voltage Regulators",
        Decimal("22.50"),
        Decimal("24000.00"),
        Decimal("180000.00"),
    ),
    (
        "BMS",
        "Battery Management & Energy Storage Modules",
        Decimal("450.00"),
        Decimal("1200.00"),
        Decimal("9500.00"),
    ),
    (
        "RADAR",
        "ADAS, Radar, LiDAR & Vision Perception",
        Decimal("280.00"),
        Decimal("2800.00"),
        Decimal("22000.00"),
    ),
    (
        "CHASSIS",
        "Braking, Steering & Active Dynamics",
        Decimal("310.00"),
        Decimal("3100.00"),
        Decimal("25000.00"),
    ),
    (
        "HARNESS",
        "High-Voltage Wiring & Busbar Distribution",
        Decimal("185.00"),
        Decimal("4500.00"),
        Decimal("35000.00"),
    ),
    (
        "THERMAL",
        "Heat Pumps, E-Compressors & Cooling Valves",
        Decimal("240.00"),
        Decimal("2200.00"),
        Decimal("17000.00"),
    ),
    (
        "COCKPIT",
        "Displays, Infotainment & Telematics ECUs",
        Decimal("380.00"),
        Decimal("1800.00"),
        Decimal("14000.00"),
    ),
    (
        "STRUCT",
        "Giga-Castings, Crash Boxes & Subframes",
        Decimal("520.00"),
        Decimal("950.00"),
        Decimal("7500.00"),
    ),
    (
        "FASTENER",
        "Precision Seals, Titanium Fasteners & Bushings",
        Decimal("12.00"),
        Decimal("42000.00"),
        Decimal("320000.00"),
    ),
]

RAW_COMPONENTS_CATALOG: list[dict[str, Any]] = []

# Index pointer for assigning plants and suppliers cyclically
_plant_codes = [p["plant_id"] for p in PLANTS_CATALOG]
_t1_node_ids = [s["neptune_node_id"] for s in RAW_SUPPLIERS_CATALOG if s["tier"] == 1]

# 1. First, insert canonical NanoCore Component (SKU-MCU-4402)
RAW_COMPONENTS_CATALOG.append(
    {
        "sku": "SKU-MCU-4402",
        "description": "32-Bit Automotive Grade Microcontroller Unit (NanoCore Cleanroom Fab)",
        "category": "MCU",
        "supplier_neptune_id": "SUP-NC-001",
        "plant_id": "PLT-MUC-01",
        "unit_cost_usd": Decimal("100.25"),
        "current_stock": Decimal("142000.00"),
        "daily_consumption_rate": Decimal("18500.00"),
        "safety_stock_units": Decimal("50000.00"),
        "inbound_eta_days": Decimal("9.00"),
        "inbound_shipment_units": Decimal("100000.00"),
        "inbound_shipment_po": "PO-NC-88921",
    }
)

# 2. Generate 199 additional distinct SKUs (20 SKUs per category, adjusting category 0 for the 1 already added)
sku_counter = 1
for cat_idx, (cat_prefix, cat_desc, base_cost, base_burn, base_stock) in enumerate(
    _CATEGORIES_METADATA
):
    # For category 0 (MCU), we already added 1 canonical SKU, so add 19 more.
    target_count = 19 if cat_idx == 0 else 20
    for item_idx in range(1, target_count + 1):
        sku_code = f"SKU-{cat_prefix}-{1000 + sku_counter}"
        # Cycle plant and supplier
        assigned_plant = _plant_codes[sku_counter % len(_plant_codes)]
        assigned_supplier = _t1_node_ids[sku_counter % len(_t1_node_ids)]

        # Deterministic variation
        cost_mult = Decimal(str(1.0 + (sku_counter % 7) * 0.08))
        burn_mult = Decimal(str(1.0 + (sku_counter % 5) * 0.12))
        stock_mult = Decimal(str(1.0 + (sku_counter % 6) * 0.15))

        cost = (base_cost * cost_mult).quantize(Decimal("0.01"))
        burn = (base_burn * burn_mult).quantize(Decimal("0.01"))
        stock = (base_stock * stock_mult).quantize(Decimal("0.01"))
        safety = (burn * Decimal("5.0")).quantize(Decimal("0.01"))
        eta = Decimal(str(3.0 + (sku_counter % 12) * 0.5)).quantize(Decimal("0.01"))
        ship_units = (burn * Decimal("8.0")).quantize(Decimal("0.01"))

        RAW_COMPONENTS_CATALOG.append(
            {
                "sku": sku_code,
                "description": f"{cat_desc} Series {item_idx:02d}",
                "category": cat_prefix,
                "supplier_neptune_id": assigned_supplier,
                "plant_id": assigned_plant,
                "unit_cost_usd": cost,
                "current_stock": stock,
                "daily_consumption_rate": burn,
                "safety_stock_units": safety,
                "inbound_eta_days": eta,
                "inbound_shipment_units": ship_units,
                "inbound_shipment_po": f"PO-GEN-{80000 + sku_counter}",
            }
        )
        sku_counter += 1


def get_raw_components_catalog() -> list[dict[str, Any]]:
    """Return immutable list of 200 component definitions."""
    return [dict(c) for c in RAW_COMPONENTS_CATALOG]


# ==============================================================================
# 4. Result Summary Dataclass
# ==============================================================================


@dataclass
class SeedDevResult:
    """Summary metrics of development database seeding execution."""

    suppliers_created: int = 0
    suppliers_updated: int = 0
    tier_1_suppliers_count: int = 0
    countries_count: int = 0
    plants_count: int = 0
    components_count: int = 0
    inventory_snapshots_count: int = 0
    alerts_count: int = 0
    nanocore_loaded: bool = False
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# 5. Core Seeder Service Function
# ==============================================================================


async def seed_database(
    session: AsyncSession,
    clear_existing: bool = False,
) -> SeedDevResult:
    """Idempotently seed the Aurora PostgreSQL database with development reference data.

    Parameters:
        session: Active asynchronous SQLAlchemy session.
        clear_existing: If True, purges existing records before seeding.

    Returns:
        SeedDevResult with counts of created/updated entities and timing.
    """
    start_time = time.perf_counter()
    result = SeedDevResult()

    logger.info(
        "Beginning development database seeding",
        extra={"clear_existing": clear_existing},
    )

    # 1. Optional purge of existing records
    if clear_existing:
        logger.info("Purging existing records across operational tables")
        await session.execute(delete(AuditLog))
        await session.execute(delete(RiskAlert))
        await session.execute(delete(InventorySnapshot))
        await session.execute(delete(Supplier))
        await session.flush()

    # 2. Seed Suppliers
    supplier_id_map: dict[str, uuid.UUID] = {}
    suppliers_created = 0
    suppliers_updated = 0

    for s_def in RAW_SUPPLIERS_CATALOG:
        node_id = s_def["neptune_node_id"]
        # Check existing by neptune_node_id
        stmt = select(Supplier).where(Supplier.neptune_node_id == node_id)
        existing = (await session.execute(stmt)).scalars().first()

        if existing is not None:
            existing.name = s_def["name"]
            existing.country_code = s_def["country_code"]
            existing.tier = s_def["tier"]
            existing.risk_score = s_def["risk_score"]
            supplier_id_map[node_id] = existing.id
            suppliers_updated += 1
        else:
            new_id = uuid.uuid4()
            supplier = Supplier(
                id=new_id,
                name=s_def["name"],
                country_code=s_def["country_code"],
                tier=s_def["tier"],
                risk_score=s_def["risk_score"],
                neptune_node_id=node_id,
            )
            session.add(supplier)
            supplier_id_map[node_id] = new_id
            suppliers_created += 1

    await session.flush()
    result.suppliers_created = suppliers_created
    result.suppliers_updated = suppliers_updated

    # Compute Tier-1 and country distribution
    t1_suppliers = [s for s in RAW_SUPPLIERS_CATALOG if s["tier"] == 1]
    result.tier_1_suppliers_count = len(t1_suppliers)
    result.countries_count = len({s["country_code"] for s in t1_suppliers})

    # 3. Seed Inventory Snapshots (200 components)
    inventory_count = 0
    plants_seen: set[str] = set()

    for c_def in RAW_COMPONENTS_CATALOG:
        sku = c_def["sku"]
        plant_id = c_def["plant_id"]
        plants_seen.add(plant_id)
        supplier_uuid = supplier_id_map.get(c_def["supplier_neptune_id"])

        # Check existing snapshot
        inv_stmt = select(InventorySnapshot).where(
            InventorySnapshot.component_sku == sku,
            InventorySnapshot.plant_id == plant_id,
        )
        existing_inv = (await session.execute(inv_stmt)).scalars().first()

        if existing_inv is not None:
            existing_inv.current_stock = c_def["current_stock"]
            existing_inv.daily_consumption_rate = c_def["daily_consumption_rate"]
            existing_inv.safety_stock_units = c_def["safety_stock_units"]
            existing_inv.unit_cost_usd = c_def["unit_cost_usd"]
            existing_inv.inbound_eta_days = c_def["inbound_eta_days"]
            existing_inv.inbound_shipment_units = c_def["inbound_shipment_units"]
            existing_inv.inbound_shipment_po = c_def["inbound_shipment_po"]
            existing_inv.supplier_id = supplier_uuid
        else:
            snapshot = InventorySnapshot(
                id=uuid.uuid4(),
                component_sku=sku,
                plant_id=plant_id,
                supplier_id=supplier_uuid,
                current_stock=c_def["current_stock"],
                daily_consumption_rate=c_def["daily_consumption_rate"],
                safety_stock_units=c_def["safety_stock_units"],
                unit_cost_usd=c_def["unit_cost_usd"],
                inbound_eta_days=c_def["inbound_eta_days"],
                inbound_shipment_units=c_def["inbound_shipment_units"],
                inbound_shipment_po=c_def["inbound_shipment_po"],
            )
            session.add(snapshot)
        inventory_count += 1

    await session.flush()
    result.components_count = len(RAW_COMPONENTS_CATALOG)
    result.inventory_snapshots_count = inventory_count
    result.plants_count = len(plants_seen)

    # 4. Seed Canonical NanoCore Disruption Scenario (Alert & Audit Log)
    nanocore_supplier_id = supplier_id_map.get("SUP-NC-001") or supplier_id_map.get("SUP-NC-882")
    nanocore_sku = "SKU-MCU-4402"

    alert_stmt = select(RiskAlert).where(RiskAlert.component_sku == nanocore_sku)
    existing_alert = (await session.execute(alert_stmt)).scalars().first()

    if existing_alert is not None:
        existing_alert.supplier_id = nanocore_supplier_id
        existing_alert.risk_level = "CRITICAL"
        existing_alert.days_of_cover = Decimal("7.68")
        existing_alert.financial_exposure = Decimal("2448105.00")
        existing_alert.shortage_volume = 24420
        existing_alert.status = "OPEN"
        alert_id = existing_alert.id
    else:
        alert_id = uuid.uuid4()
        alert = RiskAlert(
            id=alert_id,
            supplier_id=nanocore_supplier_id,
            component_sku=nanocore_sku,
            risk_level="CRITICAL",
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            status="OPEN",
        )
        session.add(alert)
        result.alerts_count = 1

    # Preserve audit log entry for NanoCore alert
    audit_stmt = select(AuditLog).where(
        AuditLog.entity_id == alert_id,
        AuditLog.action == "CREATE",
    )
    existing_audit = (await session.execute(audit_stmt)).scalars().first()

    if existing_audit is None:
        audit_entry = AuditLog(
            entity_type="risk_alerts",
            entity_id=alert_id,
            action="CREATE",
            actor_id=uuid.uuid4(),
            before_state=None,
            after_state={
                "component_sku": nanocore_sku,
                "risk_level": "CRITICAL",
                "days_of_cover": "7.68",
                "financial_exposure": "2448105.00",
                "shortage_volume": 24420,
                "status": "OPEN",
                "scenario_id": "SCENARIO-NANOCORE-001",
            },
            trace_id="trace-nanocore-seed-001",
        )
        session.add(audit_entry)

    await session.commit()
    result.nanocore_loaded = True
    result.duration_ms = (time.perf_counter() - start_time) * 1000.0

    logger.info(
        "Development database seeding completed successfully",
        extra={
            "tier_1_suppliers": result.tier_1_suppliers_count,
            "countries": result.countries_count,
            "plants": result.plants_count,
            "components": result.components_count,
            "duration_ms": result.duration_ms,
        },
    )

    return result


# ==============================================================================
# 6. Verification & Integrity Check
# ==============================================================================


async def verify_seed_integrity(session: AsyncSession) -> dict[str, Any]:
    """Audit database counts and NanoCore golden values after seeding."""
    suppliers_count = await session.scalar(select(func.count(Supplier.id)))
    tier_1_count = await session.scalar(select(func.count(Supplier.id)).where(Supplier.tier == 1))
    countries_query = await session.scalars(
        select(Supplier.country_code).where(Supplier.tier == 1).distinct()
    )
    countries = set(countries_query.all())

    inventory_count = await session.scalar(select(func.count(InventorySnapshot.id)))
    plants_query = await session.scalars(select(InventorySnapshot.plant_id).distinct())
    plants = set(plants_query.all())

    nanocore_alert = await session.scalar(
        select(RiskAlert).where(RiskAlert.component_sku == "SKU-MCU-4402")
    )

    nanocore_valid = (
        nanocore_alert is not None
        and nanocore_alert.days_of_cover == Decimal("7.68")
        and nanocore_alert.financial_exposure == Decimal("2448105.00")
        and nanocore_alert.shortage_volume == 24420
        and nanocore_alert.risk_level == "CRITICAL"
    )

    t1_val = int(tier_1_count or 0)
    inv_val = int(inventory_count or 0)

    return {
        "suppliers_count": suppliers_count,
        "tier_1_count": tier_1_count,
        "countries_count": len(countries),
        "inventory_count": inventory_count,
        "plants_count": len(plants),
        "nanocore_golden_valid": nanocore_valid,
        "all_checks_passed": (
            t1_val >= 50
            and len(countries) >= 10
            and inv_val >= 200
            and len(plants) == 20
            and nanocore_valid
        ),
    }


# ==============================================================================
# 7. CLI Main Entrypoint
# ==============================================================================


async def async_main(args: argparse.Namespace) -> int:
    """Async main routine coordinating CLI parameters."""
    print("=" * 72)
    print("ApexMotion Supplier Risk Intelligence — Development Data Seeder")
    print("=" * 72)

    if args.dry_run:
        print("[DRY-RUN] Validating in-memory seed catalogs...")
        suppliers = get_raw_suppliers_catalog()
        plants = get_plants_catalog()
        components = get_raw_components_catalog()

        t1 = [s for s in suppliers if s["tier"] == 1]
        c_set = {s["country_code"] for s in t1}

        print(f"  ✓ Suppliers defined: {len(suppliers)} (Tier-1: {len(t1)})")
        print(f"  ✓ Tier-1 Countries: {len(c_set)} ({', '.join(sorted(c_set))})")
        print(f"  ✓ Manufacturing Plants: {len(plants)}")
        print(f"  ✓ Component SKUs: {len(components)}")
        print("  ✓ Dry-run completed with zero database mutations.")
        return 0

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        result = await seed_database(session, clear_existing=args.clear)
        print(
            f"  ✓ Tier-1 Suppliers: {result.tier_1_suppliers_count} across {result.countries_count} countries"
        )
        print(f"  ✓ Manufacturing Plants: {result.plants_count}")
        print(f"  ✓ Components / Inventory Snapshots: {result.components_count}")
        print(
            f"  ✓ NanoCore Disruption Scenario: {'LOADED' if result.nanocore_loaded else 'FAILED'}"
        )
        print(f"  ✓ Seeding Duration: {result.duration_ms:.2f} ms")

        if args.verify:
            print("\n[VERIFY] Auditing database integrity...")
            audit = await verify_seed_integrity(session)
            print(f"  ✓ Integrity audit result: {audit}")
            if not audit["all_checks_passed"]:
                print("  ✗ Verification failed!")
                return 1

    print("=" * 72)
    print("Database seeding completed successfully.")
    print("=" * 72)
    return 0


def main() -> None:
    """Synchronous CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Seed development database with 50+ Tier-1 suppliers, 200 components, 20 plants, and NanoCore scenario.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Purge existing records before seeding.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate catalogs in-memory without database mutations.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run post-seed integrity audit.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
