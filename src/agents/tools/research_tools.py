"""Specialized Intelligence Research Tools (P9-3).

Enforces:
- Layering Invariants (CLAUDE.md Sec 5.2 & Sec 11):
  * Dedicated external intelligence gatherers: News Scraper, SEC EDGAR, Geopolitical API.
- Untrusted Input Quarantine & Prompt Injection Defense (CLAUDE.md Sec 8.1 & LLD Sec 5.2):
  * ALL raw external text (scraped articles, SEC 8-K/10-K filings, geopolitical feeds)
    MUST pass through QuarantinedReader before being exposed to LLMs or state channels.
  * Strips script tags, HTML/XML markup, non-printable ASCII control characters.
  * Neutralizes delimiter breakout tags (</untrusted_supplier_data>).
- Offline Determinism (CLAUDE.md Sec 14):
  * Offline-first simulation with zero network calls in unit test mode.
"""

import re
import threading
from dataclasses import dataclass

from src.core.logging import get_logger
from src.llm.models import CitationSourceType
from src.llm.quarantined_reader import QuarantinedReader, get_quarantined_reader

logger = get_logger("apexmotion.agents.tools.research")


# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScrapedNewsItem:
    """Quarantined news article intelligence record."""

    title: str
    content: str
    source: str
    published_at: str
    url: str | None
    quarantined_text: str
    source_type: CitationSourceType = CitationSourceType.NEWS
    confidence: float = 0.90


@dataclass(frozen=True)
class SECDiscloseItem:
    """Quarantined SEC regulatory filing disclosure (Form 8-K / 10-K / 10-Q)."""

    filing_id: str
    filing_type: str
    company_name: str
    period_of_report: str
    items_reported: str
    content: str
    quarantined_text: str
    source_type: CitationSourceType = CitationSourceType.SEC_FILING
    confidence: float = 0.95


@dataclass(frozen=True)
class GeopoliticalRiskItem:
    """Quarantined geopolitical risk assessment record."""

    risk_id: str
    country_code: str
    region: str
    category: str
    severity: str
    description: str
    quarantined_text: str
    source_type: CitationSourceType = CitationSourceType.GEOPOLITICAL_FEED
    confidence: float = 0.90


# ------------------------------------------------------------------------------
# 1. News Scraper Tool
# ------------------------------------------------------------------------------


class NewsScraperTool:
    """External news scraper with mandatory QuarantinedReader sanitization."""

    def __init__(self, reader: QuarantinedReader | None = None) -> None:
        self.reader = reader or get_quarantined_reader()

    def search(
        self,
        query: str,
        supplier_id: str | None = None,
        max_results: int = 3,
    ) -> list[ScrapedNewsItem]:
        """Search news feeds for supplier disruption signals and sanitize outputs."""
        logger.info(
            "NewsScraperTool: Searching news for query='%s' supplier='%s'", query, supplier_id
        )

        query_lower = (query or "").lower()
        sup_id = supplier_id or "unknown_supplier"
        results: list[ScrapedNewsItem] = []

        # 1. Canonical NanoCore cleanroom fire scenario
        if (
            "nanocore" in query_lower
            or "cleanroom" in query_lower
            or "fire" in query_lower
            or sup_id == "SUP-NC-001"
        ):
            raw_title = "Cleanroom Electrical Fire at NanoCore Semiconductor Fab 2 in Hsinchu"
            raw_body = (
                "Hsinchu, Taiwan — A major cleanroom electrical fire broke out in the photolithography bay of "
                "NanoCore Semiconductor's Fab 2 facility early Monday. Automated fire suppression systems were activated, "
                "leading to chemical retardant contamination of advanced lithography steppers. Production lines for "
                "28nm automotive-grade microcontrollers (MCU-X91) have been halted. Independent facility inspectors "
                "estimate cleanroom decontamination, recertification, and tool recalibration will require at least 9.0 business days."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_body,
                source_id="NEWS-REUTERS-NC-001",
                wrap_tags=True,
            )
            results.append(
                ScrapedNewsItem(
                    title=raw_title,
                    content=sanitized.inner_text,
                    source="Reuters Global Technology Digest",
                    published_at="2026-03-01T08:30:00Z",
                    url="https://reuters.com/tech/nanocore-fab-fire-2026",
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.NEWS,
                    confidence=0.95,
                )
            )

        # 2. Port congestion / logistics disruption
        elif bool(re.search(r"\b(port|congestion|customs)\b", query_lower)):
            raw_title = (
                "Container Bottlenecks and Customs Clearance Delays Impact Trans-Pacific Freight"
            )
            raw_body = (
                "Maritime shipping congestion has escalated at major container hubs, with vessel wait times "
                "exceeding 14 days and critical customs clearance holds on automotive sub-assemblies."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_body,
                source_id=f"NEWS-LOGISTICS-{sup_id}",
                wrap_tags=True,
            )
            results.append(
                ScrapedNewsItem(
                    title=raw_title,
                    content=sanitized.inner_text,
                    source="Journal of Commerce Freight Index",
                    published_at="2026-03-02T10:00:00Z",
                    url="https://joc.com/maritime/port-delays-2026",
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.NEWS,
                    confidence=0.90,
                )
            )

        # 3. Adversarial / generic query
        else:
            raw_title = f"Industry Intelligence Report: {query[:60]}"
            raw_body = f"Reported operational updates for supplier {sup_id}: {query}"
            sanitized = self.reader.sanitize(
                raw_text=raw_body,
                source_id=f"NEWS-{sup_id}",
                wrap_tags=True,
            )
            results.append(
                ScrapedNewsItem(
                    title=raw_title,
                    content=sanitized.inner_text,
                    source="Automotive Supply Chain Monitor",
                    published_at="2026-03-01T12:00:00Z",
                    url=None,
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.NEWS,
                    confidence=0.85,
                )
            )

        return results[:max_results]


# ------------------------------------------------------------------------------
# 2. SEC EDGAR Tool
# ------------------------------------------------------------------------------


class SECEDGARTool:
    """SEC EDGAR regulatory filing retrieval with mandatory QuarantinedReader sanitization."""

    def __init__(self, reader: QuarantinedReader | None = None) -> None:
        self.reader = reader or get_quarantined_reader()

    def search(
        self,
        supplier_id: str | None = None,
        supplier_name: str | None = None,
        filing_type: str = "8-K",
    ) -> list[SECDiscloseItem]:
        """Search SEC EDGAR database for material event disclosures and sanitize text."""
        sup_id = supplier_id or "unknown_supplier"
        name = supplier_name or sup_id
        logger.info(
            "SECEDGARTool: Searching filings for supplier='%s' name='%s' type=%s",
            sup_id,
            name,
            filing_type,
        )

        results: list[SECDiscloseItem] = []
        name_lower = name.lower()

        # 1. NanoCore Form 8-K scenario
        if "nanocore" in name_lower or sup_id == "SUP-NC-001":
            raw_content = (
                "FORM 8-K CURRENT REPORT.\n"
                "Item 2.01 Completion of Acquisition or Disposition of Assets / Material Operational Disruption.\n"
                "NanoCore Semiconductor Inc. reports that on March 1, 2026, an electrical fire occurred in the "
                "photolithography bay of Fab 2 in Hsinchu Science Park, Taiwan. Operations at Fab 2 have been suspended. "
                "The company has issued formal force majeure declarations under applicable supply agreements with Tier-1 automotive partners. "
                "Preliminary engineering assessments project cleanroom recertification lead time of 9.0 business days."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_content,
                source_id="SEC-8K-NANOCORE-2026",
                wrap_tags=True,
            )
            results.append(
                SECDiscloseItem(
                    filing_id="0001193125-26-048291",
                    filing_type="8-K",
                    company_name="NanoCore Semiconductor Inc.",
                    period_of_report="2026-03-01",
                    items_reported="Item 2.01: Material Operational Disruption",
                    content=sanitized.inner_text,
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.SEC_FILING,
                    confidence=0.98,
                )
            )

        # 2. Generic / Other supplier filings
        else:
            raw_content = (
                f"FORM {filing_type} REGULATORY FILING.\n"
                f"Company: {name} (CIK: 0001234567)\n"
                f"Period of Report: 2026-02-28.\n"
                f"Item 8.01: Other Events. Standard operational overview and regulatory compliance disclosures."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_content,
                source_id=f"SEC-{filing_type}-{sup_id}",
                wrap_tags=True,
            )
            results.append(
                SECDiscloseItem(
                    filing_id=f"0000000000-26-{sup_id[:8]}",
                    filing_type=filing_type,
                    company_name=name,
                    period_of_report="2026-02-28",
                    items_reported="Item 8.01: Other Events",
                    content=sanitized.inner_text,
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.SEC_FILING,
                    confidence=0.90,
                )
            )

        return results


# ------------------------------------------------------------------------------
# 3. Geopolitical API Tool
# ------------------------------------------------------------------------------


class GeopoliticalAPITool:
    """Geopolitical risk assessment tool with mandatory QuarantinedReader sanitization."""

    def __init__(self, reader: QuarantinedReader | None = None) -> None:
        self.reader = reader or get_quarantined_reader()

    def check_risk(
        self,
        country_code: str | None = None,
        supplier_id: str | None = None,
        region: str | None = None,
    ) -> list[GeopoliticalRiskItem]:
        """Retrieve regional trade sanctions, export controls, and supply chain concentration risks."""
        code = (country_code or "TW").upper()
        sup_id = supplier_id or "unknown_supplier"
        reg = region or "East Asia"
        logger.info(
            "GeopoliticalAPITool: Checking risk for country='%s' region='%s' supplier='%s'",
            code,
            reg,
            sup_id,
        )

        results: list[GeopoliticalRiskItem] = []

        # 1. Taiwan / East Asia semiconductor corridor
        if code in ("TW", "TAIWAN") or "taiwan" in reg.lower() or sup_id == "SUP-NC-001":
            raw_desc = (
                "Regional Supply Chain Concentration Advisory: High concentration of advanced semiconductor manufacturing "
                "in Hsinchu Science Park. Taiwan Strait maritime shipping lanes subject to routine naval exercises. "
                "Bilateral export controls and tariff monitoring active for dual-use semiconductor packaging equipment."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_desc,
                source_id=f"GEO-RISK-{code}-001",
                wrap_tags=True,
            )
            results.append(
                GeopoliticalRiskItem(
                    risk_id="GEO-TW-2026-01",
                    country_code="TW",
                    region="East Asia",
                    category="EXPORT_CONTROL",
                    severity="HIGH",
                    description=sanitized.inner_text,
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.GEOPOLITICAL_FEED,
                    confidence=0.92,
                )
            )

        # 2. General regional risk
        else:
            raw_desc = (
                f"Geopolitical risk evaluation for country {code} ({reg}): "
                "Standard border customs monitoring; no active embargoes or OFAC sanctions."
            )
            sanitized = self.reader.sanitize(
                raw_text=raw_desc,
                source_id=f"GEO-RISK-{code}",
                wrap_tags=True,
            )
            results.append(
                GeopoliticalRiskItem(
                    risk_id=f"GEO-{code}-2026-GEN",
                    country_code=code,
                    region=reg,
                    category="TRADE_MONITORING",
                    severity="LOW",
                    description=sanitized.inner_text,
                    quarantined_text=sanitized.sanitized_text,
                    source_type=CitationSourceType.GEOPOLITICAL_FEED,
                    confidence=0.85,
                )
            )

        return results


# ------------------------------------------------------------------------------
# Thread-safe Singletons
# ------------------------------------------------------------------------------

_news_tool_instance: NewsScraperTool | None = None
_news_tool_lock = threading.Lock()

_sec_tool_instance: SECEDGARTool | None = None
_sec_tool_lock = threading.Lock()

_geo_tool_instance: GeopoliticalAPITool | None = None
_geo_tool_lock = threading.Lock()


def get_news_scraper_tool() -> NewsScraperTool:
    """Return the thread-safe singleton instance of NewsScraperTool."""
    global _news_tool_instance
    if _news_tool_instance is None:
        with _news_tool_lock:
            if _news_tool_instance is None:
                _news_tool_instance = NewsScraperTool()
    return _news_tool_instance


def get_sec_edgar_tool() -> SECEDGARTool:
    """Return the thread-safe singleton instance of SECEDGARTool."""
    global _sec_tool_instance
    if _sec_tool_instance is None:
        with _sec_tool_lock:
            if _sec_tool_instance is None:
                _sec_tool_instance = SECEDGARTool()
    return _sec_tool_instance


def get_geopolitical_api_tool() -> GeopoliticalAPITool:
    """Return the thread-safe singleton instance of GeopoliticalAPITool."""
    global _geo_tool_instance
    if _geo_tool_instance is None:
        with _geo_tool_lock:
            if _geo_tool_instance is None:
                _geo_tool_instance = GeopoliticalAPITool()
    return _geo_tool_instance
