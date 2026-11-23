"""vLLM Confidential Contract Client & Data Sovereignty Router (P8-4).

Architectural Invariants & Governance:
- Data Sovereignty Enforcement (NFR-SEC-02, CLAUDE.md Sec 5.2):
  * EU-regulated & GDPR-governed contracts must NEVER leave the private VPC or be sent
    to external cloud model providers (such as Amazon Bedrock Claude).
  * Routes exclusively to self-hosted vLLM GPU clusters (e.g. 2x g6e.12xlarge on AWS EKS).
  * Strict gate: attempting to route EU-regulated or confidential contracts to external Bedrock
    raises VLLMDataSovereigntyViolationError.
- Deterministic Offline Isolation (USE_MOCK_LLM=true, GAP-002):
  * In dev and offline tests where GPU clusters are not provisioned, executes zero external I/O
    and returns schema-validated ContractAnalysis models.
- OpenAI-Compatible vLLM Protocol:
  * Interacts with /v1/chat/completions with response_format={"type": "json_object"}.
  * Retries transient connection errors with exponential backoff and propagates trace_id.
- Audit & Cryptographic Hashing (BR-RULE-007):
  * Contracts are cryptographically hashed with SHA-256 for audit trail validation.
  * Raw confidential contract text is NEVER written to unencrypted logs or stdout.
- Monetary Precision (BR-RULE-001):
  * Penalty rates, liability caps, and financial terms strictly preserve Decimal precision.
"""

import asyncio
import hashlib
import threading
import time
from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import Settings, get_settings
from src.core.logging import get_logger, get_trace_id
from src.llm.gateway import (
    LiteLLMGateway,
    LLMGatewayError,
    LLMResponse,
    TaskType,
)
from src.llm.models import (
    Citation,
    CitationSourceType,
    ContractAnalysis,
    StructuredOutputParsingError,
    parse_structured_llm_response,
)

logger = get_logger("apexmotion.llm.vllm")

# ------------------------------------------------------------------------------
# EU & EEA Member State ISO Country Codes
# ------------------------------------------------------------------------------

EU_EEA_JURISDICTIONS: frozenset[str] = frozenset(
    {
        "EU",
        "EEA",
        "EUROPE",
        "DE",  # Germany
        "FR",  # France
        "IT",  # Italy
        "ES",  # Spain
        "NL",  # Netherlands
        "BE",  # Belgium
        "SE",  # Sweden
        "PL",  # Poland
        "AT",  # Austria
        "DK",  # Denmark
        "FI",  # Finland
        "IE",  # Ireland
        "PT",  # Portugal
        "GR",  # Greece
        "CZ",  # Czech Republic
        "RO",  # Romania
        "HU",  # Hungary
        "SK",  # Slovakia
        "BG",  # Bulgaria
        "HR",  # Croatia
        "LT",  # Lithuania
        "SI",  # Slovenia
        "LV",  # Latvia
        "EE",  # Estonia
        "CY",  # Cyprus
        "LU",  # Luxembourg
        "MT",  # Malta
        "NO",  # Norway (EEA)
        "IS",  # Iceland (EEA)
        "LI",  # Liechtenstein (EEA)
    }
)


# ------------------------------------------------------------------------------
# Domain Models & Metadata
# ------------------------------------------------------------------------------


class ContractClassification(StrEnum):
    """Document sensitivity classification levels."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    HIGHLY_CONFIDENTIAL = "HIGHLY_CONFIDENTIAL"


class ContractMetadata(BaseModel):
    """Contextual metadata governing contract handling and data sovereignty routing."""

    supplier_id: str = Field(..., description="Target supplier identifier")
    contract_id: str | None = Field(default=None, description="Contract reference number")
    jurisdiction: str = Field(
        default="GLOBAL",
        description="Governing legal jurisdiction / ISO country code",
    )
    classification: ContractClassification | str = Field(
        default=ContractClassification.INTERNAL,
        description="Information security classification tier",
    )
    is_eu_regulated: bool = Field(
        default=False,
        description="Whether contract is governed by EU data protection (GDPR, CSDDD, etc.)",
    )
    is_confidential: bool = Field(
        default=False,
        description="Explicit confidentiality flag mandating VPC-only inference",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    def is_sovereign_protected(self) -> bool:
        """Determine whether contract data is subject to mandatory VPC-only residency."""
        if self.is_eu_regulated or self.is_confidential:
            return True

        classification_upper = str(self.classification).upper()
        if classification_upper in (
            ContractClassification.HIGHLY_CONFIDENTIAL,
            ContractClassification.CONFIDENTIAL,
            ContractClassification.RESTRICTED,
            "HIGHLY_CONFIDENTIAL",
            "CONFIDENTIAL",
            "RESTRICTED",
        ):
            return True

        if self.jurisdiction.upper() in EU_EEA_JURISDICTIONS:
            return True

        return False


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class VLLMClientError(LLMGatewayError):
    """Base exception for self-hosted vLLM inference errors."""

    def __init__(
        self,
        message: str,
        code: str = "VLLM_CLIENT_ERROR",
        status_code: int = 500,
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
        )


class VLLMConnectionError(VLLMClientError):
    """Raised when self-hosted vLLM GPU cluster is unreachable or returns 5xx (HTTP 503)."""

    def __init__(
        self,
        message: str = "Self-hosted vLLM cluster connection failed or service unavailable",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class VLLMTimeoutError(VLLMClientError):
    """Raised when vLLM request exceeds execution deadline (HTTP 504)."""

    def __init__(
        self,
        message: str = "vLLM GPU cluster execution deadline exceeded",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="GATEWAY_TIMEOUT",
            status_code=504,
            details=details,
        )


class VLLMDataSovereigntyViolationError(VLLMClientError):
    """Raised when confidential or EU-regulated data is routed to external cloud APIs (HTTP 403)."""

    def __init__(
        self,
        message: str = "EU-regulated or confidential contract data cannot be transmitted outside private VPC",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DATA_SOVEREIGNTY_VIOLATION",
            status_code=403,
            details=details,
        )


class VLLMContractExtractionError(VLLMClientError):
    """Raised when vLLM output fails to conform to ContractAnalysis schema (HTTP 422)."""

    def __init__(
        self,
        message: str = "Failed to extract valid structured contract clauses from vLLM output",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONTRACT_EXTRACTION_FAILED",
            status_code=422,
            details=details,
        )


# ------------------------------------------------------------------------------
# vLLM Client Implementation
# ------------------------------------------------------------------------------


class VLLMClient:
    """High-throughput client for self-hosted vLLM GPU inference inside private VPC.

    Enforces data sovereignty by ensuring confidential contract texts never traverse
    public cloud provider endpoints.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        use_mock: bool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = (base_url or self.settings.VLLM_BASE_URL).rstrip("/")
        self.model = (
            model
            or getattr(self.settings, "VLLM_MODEL", None)
            or "meta-llama/Llama-3.1-70B-Instruct"
        )
        configured_key = getattr(self.settings, "VLLM_API_KEY", None)
        self.api_key = (
            api_key or (configured_key.get_secret_value() if configured_key else None) or None
        )
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.use_mock = use_mock if use_mock is not None else self.settings.USE_MOCK_LLM

    async def health_check(self) -> bool:
        """Verify connectivity and readiness of the self-hosted vLLM GPU endpoint."""
        if self.use_mock:
            return True

        endpoint = f"{self.base_url}/health"
        headers: dict[str, str] = {}
        trace_id = get_trace_id()
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(endpoint, headers=headers)
                return response.status_code == 200
        except Exception as exc:
            logger.warning("vLLM health check probe failed: %s", exc)
            return False

    def _generate_mock_contract_analysis(
        self,
        metadata: ContractMetadata,
        contract_text: str,
    ) -> ContractAnalysis:
        """Produce deterministic, high-fidelity contract analysis for offline tests."""
        # Detect notice period or default
        notice_days = 14
        if "14 days notice" in contract_text.lower() or "14 days" in contract_text.lower():
            notice_days = 14
        elif (
            "30 days notice" in contract_text.lower() or "notice: 30 days" in contract_text.lower()
        ):
            notice_days = 30
        elif "60 days notice" in contract_text.lower():
            notice_days = 60

        # Detect payment terms
        payment_terms = "Net 30"
        if "net 60" in contract_text.lower():
            payment_terms = "Net 60"
        elif "net 90" in contract_text.lower():
            payment_terms = "Net 90"

        # Detect air freight liability
        air_freight = "SUPPLIER"
        if "split" in contract_text.lower():
            air_freight = "SPLIT_50_50"
        elif "apexmotion" in contract_text.lower() and "buyer bears" in contract_text.lower():
            air_freight = "APEXMOTION"

        # Detect force majeure
        has_fm = "force majeure" in contract_text.lower()
        fm_clause = (
            "Section 15 Force Majeure: Unforeseen cleanroom fires and natural disasters shall "
            "constitute Force Majeure excusing timely performance."
            if has_fm
            else None
        )

        return ContractAnalysis(
            supplier_id=metadata.supplier_id,
            contract_id=metadata.contract_id or f"CNT-{metadata.jurisdiction}-2024-001",
            payment_terms=payment_terms,
            notice_period_days=notice_days,
            delay_penalty_percentage_per_day=Decimal("0.02"),
            air_freight_surcharge_liability=air_freight,
            has_force_majeure=has_fm,
            force_majeure_clause=fm_clause,
            alternate_suppliers_authorized=["TSMC", "GlobalFoundries", "Samsung Foundry"],
            liability_cap_usd=Decimal("5000000.00"),
            citations=[
                Citation(
                    source_id=metadata.contract_id or f"CNT-{metadata.jurisdiction}-2024-001",
                    source_type=CitationSourceType.CONTRACT,
                    document_name="Master Supply Agreement",
                    page_or_section="Section 4.1",
                    verbatim_quote=f"Payment terms established at {payment_terms}.",
                ),
                Citation(
                    source_id=metadata.contract_id or f"CNT-{metadata.jurisdiction}-2024-001",
                    source_type=CitationSourceType.CONTRACT,
                    document_name="Master Supply Agreement",
                    page_or_section="Section 7.3",
                    verbatim_quote=f"Supplier shall provide {notice_days} days notice for delivery delays.",
                ),
                Citation(
                    source_id=metadata.contract_id or f"CNT-{metadata.jurisdiction}-2024-001",
                    source_type=CitationSourceType.CONTRACT,
                    document_name="Master Supply Agreement",
                    page_or_section="Section 8.2",
                    verbatim_quote="Delay penalty fixed at 0.02% per business day.",
                ),
            ],
        )

    def _generate_mock_completion(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[str, int, int]:
        """Construct deterministic mock completion payload."""
        content = messages[-1].get("content", "")
        supplier_id = "SUP-001"
        for word in content.split():
            if word.startswith("SUP-"):
                supplier_id = word.strip(".,;:\"'")
                break

        mock_analysis = self._generate_mock_contract_analysis(
            metadata=ContractMetadata(supplier_id=supplier_id),
            contract_text=content,
        )
        json_content = mock_analysis.model_dump_json(indent=2)
        p_tok = max(10, len(content) // 4)
        c_tok = max(15, len(json_content) // 4)
        return json_content, p_tok, c_tok

    async def acomplete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Asynchronously call vLLM /v1/chat/completions API with retries and trace propagation."""
        start_time = time.perf_counter()
        trace_id = get_trace_id()

        # 1. Offline Mock Mode
        if self.use_mock:
            json_text, prompt_tok, comp_tok = self._generate_mock_completion(messages)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return LLMResponse(
                content=json_text,
                model=self.model,
                prompt_tokens=prompt_tok,
                completion_tokens=comp_tok,
                total_tokens=prompt_tok + comp_tok,
                cost_usd=Decimal("0.000000"),  # Self-hosted internal compute = 0 direct token fee
                latency_ms=round(latency_ms, 2),
                is_fallback=False,
                is_cached=False,
                trace_id=trace_id,
                metadata={"provider": "vllm_local", "mock": True},
            )

        # 2. Live vLLM Execution
        endpoint = f"{self.base_url}/v1/chat/completions"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format or {"type": "json_object"},
            **kwargs,
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)

                    if resp.status_code >= 500:
                        raise VLLMConnectionError(
                            f"vLLM server error (HTTP {resp.status_code}): {resp.text}",
                            details={"status_code": resp.status_code, "attempt": attempt},
                        )

                    if resp.status_code != 200:
                        raise VLLMClientError(
                            f"vLLM client error (HTTP {resp.status_code}): {resp.text}",
                            status_code=resp.status_code,
                            details={"attempt": attempt},
                        )

                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise VLLMContractExtractionError(
                            "vLLM response contains no completion choices"
                        )

                    content = choices[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    p_tok = int(usage.get("prompt_tokens", 0))
                    c_tok = int(usage.get("completion_tokens", 0))

                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    return LLMResponse(
                        content=content,
                        model=self.model,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        total_tokens=p_tok + c_tok,
                        cost_usd=Decimal("0.000000"),
                        latency_ms=round(latency_ms, 2),
                        is_fallback=False,
                        is_cached=False,
                        trace_id=trace_id,
                        metadata={"provider": "vllm_local", "vllm_id": data.get("id")},
                    )

            except httpx.TimeoutException as exc:
                last_error = VLLMTimeoutError(
                    f"vLLM cluster timeout exceeded ({self.timeout_seconds}s) on attempt {attempt}: {exc}",
                    details={"attempt": attempt},
                )
            except httpx.ConnectError as exc:
                last_error = VLLMConnectionError(
                    f"Failed to connect to vLLM endpoint {self.base_url} on attempt {attempt}: {exc}",
                    details={"attempt": attempt},
                )
            except (VLLMConnectionError, VLLMTimeoutError, VLLMClientError) as exc:
                last_error = exc
            except Exception as exc:
                last_error = VLLMClientError(f"Unexpected error communicating with vLLM: {exc}")
                break

            if attempt < self.max_retries:
                backoff = 0.2 * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

        raise last_error or VLLMConnectionError("vLLM request failed after maximum retries")

    async def extract_contract_clauses(
        self,
        contract_text: str,
        metadata: ContractMetadata | dict[str, Any],
        prompt_override: str | None = None,
    ) -> ContractAnalysis:
        """Extract typed, schema-validated ContractAnalysis clauses from contract text.

        Enforces SHA-256 audit logging while strictly preventing exposure of raw contract
        content in logs or unencrypted stores (BR-RULE-007).
        """
        if not contract_text or not contract_text.strip():
            raise VLLMContractExtractionError("Contract text cannot be empty or whitespace")

        meta = metadata if isinstance(metadata, ContractMetadata) else ContractMetadata(**metadata)

        # Cryptographic content hashing for immutable audit trail
        contract_hash = hashlib.sha256(contract_text.encode("utf-8")).hexdigest()
        logger.info(
            "Initiating confidential contract extraction for supplier %s (contract_hash=%s, jurisdiction=%s)",
            meta.supplier_id,
            contract_hash[:12],
            meta.jurisdiction,
        )

        # In offline mock mode, bypass raw completion formatting for instantaneous schema return
        if self.use_mock:
            analysis = self._generate_mock_contract_analysis(meta, contract_text)
            logger.debug(
                "Mock contract extraction successful for supplier %s (contract_hash=%s)",
                meta.supplier_id,
                contract_hash[:12],
            )
            return analysis

        system_instruction = (
            "You are a Senior Legal Counsel and Contract Intelligence AI for ApexMotion Mobility.\n"
            "Your task is to extract critical supply chain and risk provisions from the provided supplier contract.\n"
            "You must return ONLY a single, valid JSON object matching the ContractAnalysis schema.\n"
            "Strict requirements:\n"
            "- Extract: supplier_id, contract_id, payment_terms, notice_period_days, delay_penalty_percentage_per_day,\n"
            "  air_freight_surcharge_liability, has_force_majeure, force_majeure_clause,\n"
            "  alternate_suppliers_authorized, liability_cap_usd, and citations.\n"
            "- Delay penalty must be expressed as a decimal string representing the daily percentage (e.g. '0.02' for 0.02%).\n"
            "- Air freight liability must be one of: 'SUPPLIER', 'APEXMOTION', 'SPLIT_50_50', 'UNSPECIFIED'.\n"
            "- Do not output markdown code blocks or conversational commentary."
        )

        user_content = prompt_override or (
            f"Supplier ID: {meta.supplier_id}\n"
            f"Contract ID: {meta.contract_id or 'UNKNOWN'}\n"
            f"Jurisdiction: {meta.jurisdiction}\n"
            f"Classification: {meta.classification}\n\n"
            f"Contract Document:\n{contract_text}"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ]

        response = await self.acomplete(
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        try:
            analysis = parse_structured_llm_response(response.content, ContractAnalysis)
            logger.info(
                "Successfully extracted contract clauses for supplier %s (tokens=%d, latency=%.2fms)",
                meta.supplier_id,
                response.total_tokens,
                response.latency_ms,
            )
            return analysis
        except (StructuredOutputParsingError, Exception) as exc:
            logger.error(
                "Contract analysis parsing failed for supplier %s: %s",
                meta.supplier_id,
                exc,
            )
            raise VLLMContractExtractionError(
                f"Failed to parse vLLM output into ContractAnalysis: {exc}",
                details={"contract_hash": contract_hash, "raw_content": response.content[:200]},
            ) from exc


# ------------------------------------------------------------------------------
# Confidential Contract Router (Data Sovereignty Orchestration)
# ------------------------------------------------------------------------------


class ConfidentialContractRouter:
    """Intelligent router enforcing data sovereignty for supplier contract analysis.

    Directs EU-regulated and confidential agreements exclusively to the private VPC vLLM cluster,
    routing standard non-sensitive agreements to the Bedrock LiteLLM gateway.
    """

    def __init__(
        self,
        vllm_client: VLLMClient | None = None,
        litellm_gateway: LiteLLMGateway | None = None,
        use_mock: bool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.use_mock = use_mock if use_mock is not None else self.settings.USE_MOCK_LLM
        self.vllm_client = vllm_client or VLLMClient(
            settings=self.settings,
            use_mock=self.use_mock,
        )
        self.litellm_gateway = litellm_gateway or LiteLLMGateway(
            settings=self.settings,
            use_mock=self.use_mock,
        )

    def route_contract(self, metadata: ContractMetadata | dict[str, Any]) -> str:
        """Evaluate contract sensitivity and return target inference engine ('vllm' or 'bedrock')."""
        meta = metadata if isinstance(metadata, ContractMetadata) else ContractMetadata(**metadata)
        if meta.is_sovereign_protected():
            return "vllm"
        return "bedrock"

    async def process_contract(
        self,
        contract_text: str,
        metadata: ContractMetadata | dict[str, Any],
        force_target: str | None = None,
    ) -> ContractAnalysis:
        """Route contract extraction to the compliant inference provider.

        CRITICAL SECURITY INVARIANT:
        If the contract is EU-regulated or confidential, ANY attempt to force or route
        it to Bedrock triggers VLLMDataSovereigntyViolationError (HTTP 403).
        """
        meta = metadata if isinstance(metadata, ContractMetadata) else ContractMetadata(**metadata)

        is_sovereign = meta.is_sovereign_protected()
        chosen_target = force_target.lower() if force_target else self.route_contract(meta)

        # Enforce strict sovereignty boundary
        if is_sovereign and chosen_target == "bedrock":
            error_msg = (
                f"CRITICAL DATA SOVEREIGNTY VIOLATION: Contract for supplier '{meta.supplier_id}' "
                f"(jurisdiction='{meta.jurisdiction}', classification='{meta.classification}') "
                f"is an EU-regulated or confidential contract and is strictly prohibited from being "
                f"sent to external cloud provider Bedrock."
            )
            logger.error(error_msg)
            raise VLLMDataSovereigntyViolationError(error_msg)

        if chosen_target == "vllm":
            return await self.vllm_client.extract_contract_clauses(contract_text, meta)

        # Non-confidential commercial document routing via Bedrock LiteLLM Gateway
        logger.info(
            "Routing standard commercial contract for supplier %s to Bedrock gateway",
            meta.supplier_id,
        )
        if self.use_mock or self.litellm_gateway.use_mock:
            # Deterministic offline mock response for ContractAnalysis
            return self.vllm_client._generate_mock_contract_analysis(meta, contract_text)

        extraction_prompt = (
            "Extract structured contract clauses according to ContractAnalysis schema.\n"
            f"Supplier ID: {meta.supplier_id}\n"
            f"Contract Document:\n{contract_text}"
        )
        response = await self.litellm_gateway.acomplete(
            prompt=extraction_prompt,
            task_type=TaskType.EXTRACTION,
        )
        return parse_structured_llm_response(response.content, ContractAnalysis)


# ------------------------------------------------------------------------------
# Singletons & Dependency Injection
# ------------------------------------------------------------------------------

_vllm_client_lock = threading.Lock()
_global_vllm_client: VLLMClient | None = None

_router_lock = threading.Lock()
_global_contract_router: ConfidentialContractRouter | None = None


def get_vllm_client() -> VLLMClient:
    """Return thread-safe singleton instance of VLLMClient."""
    global _global_vllm_client
    if _global_vllm_client is None:
        with _vllm_client_lock:
            if _global_vllm_client is None:
                _global_vllm_client = VLLMClient()
    return _global_vllm_client


def get_contract_router() -> ConfidentialContractRouter:
    """Return thread-safe singleton instance of ConfidentialContractRouter."""
    global _global_contract_router
    if _global_contract_router is None:
        with _router_lock:
            if _global_contract_router is None:
                _global_contract_router = ConfidentialContractRouter()
    return _global_contract_router
