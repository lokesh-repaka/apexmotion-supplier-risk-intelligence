"""Unit tests for OpenSearch Vector Seeding & Contract Clause Catalog (P13-4).

Verifies:
- 500 synthetic contract clauses generated across 50 Tier-1 automotive suppliers (10 countries).
- Exact distribution of 50 clauses per category across all 10 legal categories.
- 1536-dimensional L2-normalized dense embedding vectors.
- Semantic clustering ensuring high cosine similarity for identical categories and low for disparate categories.
- High-fidelity preservation of canonical NanoCore and BetaElectro contract terms.
- Batch bulk indexing into `contracts-v1` index matching LLD Section 3.2 k-NN schema.
- Comprehensive post-seed integrity verification and k-NN search smoke-testing.
- Dry-run CLI execution with zero external I/O.
- 100% offline isolation with zero external network or AWS dependencies.
"""

import argparse
import math
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from src.database.opensearch_client import OpenSearchClient
from src.database.seed_opensearch import (
    CLAUSE_CATEGORIES,
    EMBEDDING_DIMENSION,
    SUPPLIERS_METADATA,
    ContractClause,
    OpenSearchSeedResult,
    async_main,
    build_synthetic_contract_clauses,
    generate_deterministic_vector,
    main,
    seed_opensearch,
    verify_opensearch_seed_integrity,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ------------------------------------------------------------------------------
# 1. Clause Catalog Generation Tests
# ------------------------------------------------------------------------------


def test_build_synthetic_contract_clauses_exact_500_count() -> None:
    """Verify that exactly 500 synthetic contract clauses are generated."""
    clauses = build_synthetic_contract_clauses()

    assert len(clauses) == 500, f"Expected 500 clauses, got {len(clauses)}"
    assert len(SUPPLIERS_METADATA) == 50, f"Expected 50 suppliers, got {len(SUPPLIERS_METADATA)}"
    assert len(CLAUSE_CATEGORIES) == 10, f"Expected 10 categories, got {len(CLAUSE_CATEGORIES)}"

    # Verify unique chunk IDs
    chunk_ids = {c.chunk_id for c in clauses}
    assert len(chunk_ids) == 500, "All 500 chunk IDs must be globally unique"

    # Verify unique contract IDs and supplier IDs
    contract_ids = {c.contract_id for c in clauses}
    supplier_ids = {c.supplier_id for c in clauses}
    assert len(contract_ids) == 50
    assert len(supplier_ids) == 50

    # Verify uniform distribution across all 10 categories (50 per category)
    category_counts: dict[str, int] = {}
    for c in clauses:
        category_counts[c.clause_category] = category_counts.get(c.clause_category, 0) + 1

    for category in CLAUSE_CATEGORIES:
        assert category_counts[category] == 50, (
            f"Expected exactly 50 clauses for category {category}, got {category_counts.get(category)}"
        )


def test_clause_embedding_vector_dimensions_and_normalization() -> None:
    """Verify all embedding vectors are 1536-dimensional and L2-normalized."""
    clauses = build_synthetic_contract_clauses()

    # Check a representative sample across various suppliers
    sample_indices = [0, 4, 9, 50, 100, 250, 499]
    for idx in sample_indices:
        clause = clauses[idx]
        vec = clause.embedding_vector

        assert len(vec) == EMBEDDING_DIMENSION, f"Expected 1536 dimensions, got {len(vec)}"
        assert isinstance(vec[0], float)

        # L2 norm must be approximately 1.0 (unit vector)
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4, f"Vector norm {norm} deviates from 1.0 unit length"


def test_semantic_clustering_cosine_similarity() -> None:
    """Verify vectors in the same category exhibit high similarity while cross-category exhibit low."""
    # Two clauses in the same category (e.g. FORCE_MAJEURE)
    v_fm_1 = generate_deterministic_vector("test-doc-fm-1", category_idx=4)
    v_fm_2 = generate_deterministic_vector("test-doc-fm-2", category_idx=4)

    # One clause in a different category (e.g. PAYMENT_TERMS, index 0)
    v_pay = generate_deterministic_vector("test-doc-pay-1", category_idx=0)

    # Cosine similarity for unit vectors is simply dot product
    dot_same = sum(a * b for a, b in zip(v_fm_1, v_fm_2, strict=True))
    dot_diff = sum(a * b for a, b in zip(v_fm_1, v_pay, strict=True))

    # Same category should cluster closely (> 0.85)
    assert dot_same > 0.85, f"Expected high intra-category similarity, got {dot_same}"

    # Different categories should be nearly orthogonal (< 0.20)
    assert dot_diff < 0.20, f"Expected low inter-category similarity, got {dot_diff}"


def test_canonical_nanocore_and_betaelectro_clauses_present() -> None:
    """Verify that canonical NanoCore and BetaElectro terms match golden scenario requirements."""
    clauses = build_synthetic_contract_clauses()
    clause_map = {c.chunk_id: c for c in clauses}

    # 1. NanoCore Semiconductor (CTR-NC-2024-01)
    # Chunk 005: Force Majeure
    nc_fm = clause_map.get("CHK-CTR-NC-2024-01-005")
    assert nc_fm is not None
    assert nc_fm.clause_category == "FORCE_MAJEURE"
    assert nc_fm.section_reference == "Section 15.2"
    assert "facility fires" in nc_fm.text_content
    assert "cleanroom contamination" in nc_fm.text_content
    assert "48 hours" in nc_fm.text_content

    # Chunk 004: Expedited Logistics
    nc_fr = clause_map.get("CHK-CTR-NC-2024-01-004")
    assert nc_fr is not None
    assert nc_fr.clause_category == "EXPEDITED_FREIGHT"
    assert "100% liability" in nc_fr.text_content
    assert "air freight" in nc_fr.text_content

    # Chunk 006: Alternate Sourcing
    nc_alt = clause_map.get("CHK-CTR-NC-2024-01-006")
    assert nc_alt is not None
    assert "TSMC" in nc_alt.text_content
    assert "GlobalFoundries" in nc_alt.text_content

    # 2. BetaElectro AG (CTR-BE-2023-09)
    # Chunk 004: Expedited Freight
    be_fr = clause_map.get("CHK-CTR-BE-2023-09-004")
    assert be_fr is not None
    assert "SPLIT_50_50" in be_fr.text_content

    # Chunk 006: Secondary Sourcing
    be_alt = clause_map.get("CHK-CTR-BE-2023-09-006")
    assert be_alt is not None
    assert "MicroChip Global" in be_alt.text_content


def test_contract_clause_to_doc_format() -> None:
    """Verify ContractClause.to_doc() produces dictionary compatible with OpenSearch mapping."""
    clause = ContractClause(
        chunk_id="CHK-TEST-001",
        contract_id="CTR-TEST-01",
        supplier_id="SUP-TEST-01",
        supplier_name="Test Supplier Inc",
        clause_category="FORCE_MAJEURE",
        section_reference="Section 1.1",
        page_number=1,
        text_content="Force majeure text",
        embedding_vector=[0.1] * EMBEDDING_DIMENSION,
    )
    doc = clause.to_doc()

    assert doc["chunk_id"] == "CHK-TEST-01" or doc["chunk_id"] == "CHK-TEST-001"
    assert doc["contract_id"] == "CTR-TEST-01"
    assert doc["supplier_id"] == "SUP-TEST-01"
    assert doc["clause_category"] == "FORCE_MAJEURE"
    assert doc["text_content"] == "Force majeure text"
    assert len(doc["embedding_vector"]) == EMBEDDING_DIMENSION


# ------------------------------------------------------------------------------
# 2. Seeding Service Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_opensearch_success_mock_client() -> None:
    """Verify seed_opensearch executes create_knn_index and batch bulk_upsert."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.create_knn_index.return_value = True
    mock_client.bulk_upsert.return_value = {"errors": False, "items": []}

    result = await seed_opensearch(
        client=mock_client,
        index_name="contracts-v1",
        clear_existing=False,
        batch_size=100,
    )

    assert isinstance(result, OpenSearchSeedResult)
    assert result.success is True
    assert result.total_clauses == 500
    assert result.total_contracts == 50
    assert result.total_suppliers == 50
    assert result.batch_count == 5  # 500 / 100 = 5 batches
    assert mock_client.create_knn_index.call_count == 1
    assert mock_client.bulk_upsert.call_count == 5

    # Verify dimension argument in index creation
    _, kwargs = mock_client.create_knn_index.call_args
    assert kwargs.get("dimension") == 1536
    assert kwargs.get("space_type") == "cosinesimil"


@pytest.mark.asyncio
async def test_seed_opensearch_clear_existing() -> None:
    """Verify seed_opensearch executes delete_index when clear_existing is True."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.delete_index.return_value = True
    mock_client.create_knn_index.return_value = True
    mock_client.bulk_upsert.return_value = {"errors": False}

    await seed_opensearch(
        client=mock_client,
        index_name="contracts-v1",
        clear_existing=True,
        batch_size=250,
    )

    assert mock_client.delete_index.call_count == 1
    assert mock_client.bulk_upsert.call_count == 2  # 500 / 250 = 2 batches


# ------------------------------------------------------------------------------
# 3. Post-Seed Integrity Verification Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_success() -> None:
    """Verify verify_opensearch_seed_integrity returns is_valid=True under valid conditions."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True

    # Mock get_document for NanoCore force majeure and expedited freight
    def mock_get_doc(_index_name: str, doc_id: str) -> dict[str, Any] | None:
        if "005" in doc_id:
            return {"chunk_id": doc_id, "text_content": "facility fires and natural disasters"}
        if "004" in doc_id:
            return {"chunk_id": doc_id, "text_content": "100% liability for air freight surcharges"}
        return None

    mock_client.get_document.side_effect = mock_get_doc

    # Mock k-NN search returning top hit in FORCE_MAJEURE category
    mock_client.search_knn.return_value = [
        {
            "id": "CHK-CTR-NC-2024-01-005",
            "score": 0.94,
            "document": {"clause_category": "FORCE_MAJEURE", "text_content": "facility fires"},
        }
    ]

    # Mock underlying client count API
    mock_inner_client = AsyncMock()
    mock_inner_client.count.return_value = {"count": 500}
    mock_client.client = mock_inner_client

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")

    assert report["is_valid"] is True
    assert report["index_exists"] is True
    assert report["canonical_clauses_present"] is True
    assert report["knn_query_operational"] is True
    assert report["total_documents"] == 500
    assert len(report["discrepancies"]) == 0


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_index_missing() -> None:
    """Verify verify_opensearch_seed_integrity detects missing index."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = False

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")

    assert report["is_valid"] is False
    assert report["index_exists"] is False
    assert any("does not exist" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_canonical_missing() -> None:
    """Verify verify_opensearch_seed_integrity detects missing canonical NanoCore clauses."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True
    mock_client.get_document.return_value = None  # Missing doc

    mock_client.search_knn.return_value = [
        {"id": "CHK-1", "score": 0.9, "document": {"clause_category": "FORCE_MAJEURE"}}
    ]
    mock_inner_client = AsyncMock()
    mock_inner_client.count.return_value = {"count": 500}
    mock_client.client = mock_inner_client

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")

    assert report["is_valid"] is False
    assert report["canonical_clauses_present"] is False
    assert any("Missing canonical NanoCore clauses" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_knn_category_mismatch() -> None:
    """Verify verify_opensearch_seed_integrity detects k-NN query returning wrong category."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True
    mock_client.get_document.side_effect = lambda _idx, _doc_id: {
        "text_content": "facility fires air freight"
    }

    # k-NN query unexpectedly returned PAYMENT_TERMS instead of FORCE_MAJEURE
    mock_client.search_knn.return_value = [
        {"id": "CHK-1", "score": 0.5, "document": {"clause_category": "PAYMENT_TERMS"}}
    ]
    mock_inner_client = AsyncMock()
    mock_inner_client.count.return_value = {"count": 500}
    mock_client.client = mock_inner_client

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")

    assert report["is_valid"] is False
    assert report["knn_query_operational"] is False
    assert any("k-NN query top hit category mismatch" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_exception_handling() -> None:
    """Verify verify_opensearch_seed_integrity captures unexpected client errors gracefully."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.side_effect = RuntimeError("OpenSearch cluster timeout")

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")

    assert report["is_valid"] is False
    assert any("Audit exception" in d for d in report["discrepancies"])


# ------------------------------------------------------------------------------
# 4. CLI Dry-Run Tests
# ------------------------------------------------------------------------------


def test_seed_opensearch_script_dry_run() -> None:
    """Verify scripts/seed_opensearch.py executes cleanly in --dry-run mode."""
    script_path = REPO_ROOT / "scripts" / "seed_opensearch.py"
    assert script_path.exists(), f"Seed script {script_path} not found"

    result = subprocess.run(
        [sys.executable, str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Script failed with output: {result.stderr}"
    assert "ApexMotion OpenSearch Vector Seeder" in result.stdout
    assert "Generated 500 clauses" in result.stdout
    assert "Vector dimension: 1536" in result.stdout


def test_seed_opensearch_module_dry_run() -> None:
    """Verify python -m src.database.seed_opensearch executes cleanly in --dry-run mode."""
    result = subprocess.run(
        [sys.executable, "-m", "src.database.seed_opensearch", "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Module CLI failed with output: {result.stderr}"


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_text_mismatches() -> None:
    """Verify verify_opensearch_seed_integrity reports discrepancies when text content deviates."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True

    # Missing expected phrases in documents
    def mock_bad_get_doc(_index: str, doc_id: str) -> dict[str, Any]:
        if "005" in doc_id:
            return {"chunk_id": doc_id, "text_content": "routine schedule deviation"}
        return {"chunk_id": doc_id, "text_content": "standard rail freight"}

    mock_client.get_document.side_effect = mock_bad_get_doc
    mock_client.search_knn.return_value = [
        {"id": "1", "document": {"clause_category": "FORCE_MAJEURE"}}
    ]
    mock_client.client = AsyncMock()
    mock_client.client.count.return_value = {"count": 500}

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")
    assert report["is_valid"] is False
    assert any("force majeure text mismatch" in d for d in report["discrepancies"])
    assert any("expedited freight text mismatch" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_zero_knn_hits() -> None:
    """Verify verify_opensearch_seed_integrity reports discrepancy on empty k-NN search."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True
    mock_client.get_document.side_effect = lambda _idx, _doc_id: {
        "text_content": "facility fires air freight"
    }
    mock_client.search_knn.return_value = []  # 0 hits
    mock_client.client = AsyncMock()
    mock_client.client.count.return_value = {"count": 500}

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")
    assert report["is_valid"] is False
    assert any("returned 0 hits" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_verify_opensearch_seed_integrity_low_document_count() -> None:
    """Verify verify_opensearch_seed_integrity detects document count below 500."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.index_exists.return_value = True
    mock_client.get_document.side_effect = lambda _idx, _doc_id: {
        "text_content": "facility fires air freight"
    }
    mock_client.search_knn.return_value = [
        {"id": "1", "document": {"clause_category": "FORCE_MAJEURE"}}
    ]
    mock_client.client = AsyncMock()
    mock_client.client.count.return_value = {"count": 120}  # Less than 500

    report = await verify_opensearch_seed_integrity(mock_client, index_name="contracts-v1")
    assert report["is_valid"] is False
    assert any("expected >= 500, found 120" in d for d in report["discrepancies"])


@pytest.mark.asyncio
async def test_async_main_dry_run_direct() -> None:
    """Verify async_main directly with dry_run flag."""
    args = argparse.Namespace(
        dry_run=True,
        endpoint="http://localhost:9200",
        index_name="contracts-v1",
        clear=False,
        verify=False,
        verify_only=False,
        batch_size=100,
    )
    code = await async_main(args)
    assert code == 0


@pytest.mark.asyncio
async def test_async_main_live_with_verify_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify async_main live execution branch with seed and verify flags."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.close = AsyncMock()
    monkeypatch.setattr(
        "src.database.seed_opensearch.OpenSearchClient",
        lambda *_args, **_kwargs: mock_client,
    )

    async def mock_seed(*_args: Any, **_kwargs: Any) -> OpenSearchSeedResult:
        return OpenSearchSeedResult(
            success=True,
            index_name="contracts-v1",
            total_clauses=500,
            total_contracts=50,
            total_suppliers=50,
            categories={"FORCE_MAJEURE": 50},
            batch_count=5,
            elapsed_seconds=0.12,
        )

    async def mock_verify(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"is_valid": True, "discrepancies": []}

    monkeypatch.setattr("src.database.seed_opensearch.seed_opensearch", mock_seed)
    monkeypatch.setattr(
        "src.database.seed_opensearch.verify_opensearch_seed_integrity", mock_verify
    )

    args = argparse.Namespace(
        dry_run=False,
        endpoint="http://localhost:9200",
        index_name="contracts-v1",
        clear=True,
        verify=True,
        verify_only=False,
        batch_size=100,
    )
    code = await async_main(args)
    assert code == 0
    assert mock_client.close.call_count == 1


@pytest.mark.asyncio
async def test_async_main_verify_only_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify async_main returns code 1 when verify-only fails."""
    mock_client = AsyncMock(spec=OpenSearchClient)
    mock_client.close = AsyncMock()
    monkeypatch.setattr(
        "src.database.seed_opensearch.OpenSearchClient",
        lambda *_args, **_kwargs: mock_client,
    )

    async def mock_verify_failed(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"is_valid": False, "discrepancies": ["Index missing"]}

    monkeypatch.setattr(
        "src.database.seed_opensearch.verify_opensearch_seed_integrity", mock_verify_failed
    )

    args = argparse.Namespace(
        dry_run=False,
        endpoint="http://localhost:9200",
        index_name="contracts-v1",
        clear=False,
        verify=False,
        verify_only=True,
        batch_size=100,
    )
    code = await async_main(args)
    assert code == 1


def test_main_cli_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify main() entrypoint parses arguments and invokes async_main."""
    monkeypatch.setattr(sys, "argv", ["seed_opensearch", "--dry-run"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
