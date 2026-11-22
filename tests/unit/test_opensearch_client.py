"""Unit tests for Amazon OpenSearch vector search client (P3-5).

Verifies:
- OpenSearchClient initialization and configuration from Settings.
- k-NN index creation with HNSW cosine similarity mappings (LLD Section 3.2).
- Idempotent index creation and deletion.
- Single and bulk document upsert with 1536-dimensional embedding vectors.
- Nearest-neighbour k-NN vector search execution and hit score parsing.
- Filtered k-NN search combining semantic vector distance with metadata terms.
- Resilient error handling on cluster timeouts and missing documents.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from opensearchpy.exceptions import ConnectionError, NotFoundError
from src.database.opensearch_client import OpenSearchClient


@pytest.fixture
def mock_opensearch_py_client() -> AsyncMock:
    """Mock AsyncOpenSearch client for offline unit testing."""
    mock = AsyncMock()
    mock.indices = AsyncMock()
    return mock


@pytest.fixture
def opensearch_client(mock_opensearch_py_client: AsyncMock) -> OpenSearchClient:
    """OpenSearchClient instance wired to mock AsyncOpenSearch."""
    return OpenSearchClient(
        endpoint="http://localhost:9200",
        client=mock_opensearch_py_client,
    )


def test_client_initialization_defaults_and_custom_endpoint() -> None:
    """Verify OpenSearchClient loads endpoint from settings or accepts overrides."""
    with patch("src.database.opensearch_client.AsyncOpenSearch") as mock_cls:
        client = OpenSearchClient()
        assert client.endpoint is not None
        mock_cls.assert_called_once()

    custom = OpenSearchClient(endpoint="https://custom-opensearch.internal:9200")
    assert custom.endpoint == "https://custom-opensearch.internal:9200"


@pytest.mark.asyncio
async def test_create_knn_index_payload_and_idempotency(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify create_knn_index generates exact LLD Section 3.2 mapping and behaves idempotently."""
    mock_opensearch_py_client.indices.exists.return_value = False
    mock_opensearch_py_client.indices.create.return_value = {"acknowledged": True}

    created = await opensearch_client.create_knn_index(
        index_name="contracts-v1",
        dimension=1536,
        space_type="cosinesimil",
        ef_construction=256,
        m=16,
    )
    assert created is True
    mock_opensearch_py_client.indices.create.assert_called_once()

    call_args = mock_opensearch_py_client.indices.create.call_args[1]
    assert call_args["index"] == "contracts-v1"
    body = call_args["body"]

    # Verify settings
    assert body["settings"]["index"]["knn"] is True

    # Verify properties match LLD Section 3.2
    vector_prop = body["mappings"]["properties"]["embedding_vector"]
    assert vector_prop["type"] == "knn_vector"
    assert vector_prop["dimension"] == 1536
    assert vector_prop["method"]["name"] == "hnsw"
    assert vector_prop["method"]["space_type"] == "cosinesimil"
    assert vector_prop["method"]["engine"] == "nmslib"
    assert vector_prop["method"]["parameters"]["ef_construction"] == 256
    assert vector_prop["method"]["parameters"]["m"] == 16

    # Idempotency check: if index exists, do not recreate
    mock_opensearch_py_client.indices.exists.return_value = True
    created_again = await opensearch_client.create_knn_index("contracts-v1")
    assert created_again is False


@pytest.mark.asyncio
async def test_upsert_document_and_vector_attachment(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify upsert_document indexes document with attached embedding vector."""
    mock_opensearch_py_client.index.return_value = {
        "_id": "chunk-contract-001",
        "result": "created",
    }

    dummy_vector = [0.015] * 1536
    doc_payload = {
        "contract_id": "CNT-NC-882",
        "supplier_id": "SUP-NC-882",
        "clause_category": "FORCE_MAJEURE",
        "text_content": "Supplier shall not be liable for delayed delivery resulting from natural disaster...",
    }

    result = await opensearch_client.upsert_document(
        index_name="contracts-v1",
        doc_id="chunk-contract-001",
        document=doc_payload,
        vector=dummy_vector,
    )

    assert result["result"] == "created"
    mock_opensearch_py_client.index.assert_called_once()
    index_call = mock_opensearch_py_client.index.call_args[1]
    assert index_call["index"] == "contracts-v1"
    assert index_call["id"] == "chunk-contract-001"
    assert index_call["body"]["embedding_vector"] == dummy_vector
    assert index_call["body"]["clause_category"] == "FORCE_MAJEURE"


@pytest.mark.asyncio
async def test_bulk_upsert_documents(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify bulk_upsert formats OpenSearch bulk action payload and returns stats."""
    mock_opensearch_py_client.bulk.return_value = {
        "errors": False,
        "items": [
            {"index": {"_id": "doc-1", "status": 201}},
            {"index": {"_id": "doc-2", "status": 201}},
        ],
    }

    docs = [
        {"id": "doc-1", "text": "Clause 1", "vector": [0.1] * 1536},
        {"id": "doc-2", "text": "Clause 2", "vector": [0.2] * 1536},
    ]

    bulk_res = await opensearch_client.bulk_upsert("contracts-v1", docs)
    assert bulk_res["errors"] is False
    assert len(bulk_res["items"]) == 2
    mock_opensearch_py_client.bulk.assert_called_once()


@pytest.mark.asyncio
async def test_knn_search_query_generation_and_result_parsing(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify search_knn constructs valid k-NN DSL query and parses search hits."""
    mock_opensearch_py_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": "chunk-contract-001",
                    "_score": 0.892,
                    "_source": {
                        "contract_id": "CNT-NC-882",
                        "clause_category": "FORCE_MAJEURE",
                        "text_content": "Force majeure clause text...",
                    },
                }
            ],
        }
    }

    query_vector = [0.01] * 1536
    results = await opensearch_client.search_knn(
        index_name="contracts-v1",
        query_vector=query_vector,
        k=3,
    )

    assert len(results) == 1
    hit = results[0]
    assert hit["id"] == "chunk-contract-001"
    assert hit["score"] == 0.892
    assert hit["document"]["contract_id"] == "CNT-NC-882"

    search_args = mock_opensearch_py_client.search.call_args[1]
    assert search_args["index"] == "contracts-v1"
    assert search_args["body"]["size"] == 3
    assert search_args["body"]["query"]["knn"]["embedding_vector"]["k"] == 3
    assert search_args["body"]["query"]["knn"]["embedding_vector"]["vector"] == query_vector


@pytest.mark.asyncio
async def test_knn_search_with_filter_criteria(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify search_knn applies boolean metadata filtering alongside vector query."""
    mock_opensearch_py_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": "chunk-contract-002",
                    "_score": 0.945,
                    "_source": {
                        "contract_id": "CNT-NC-882",
                        "supplier_id": "SUP-NC-882",
                        "clause_category": "LIABILITY_CAP",
                    },
                }
            ],
        }
    }

    query_vector = [0.05] * 1536
    filter_criteria: dict[str, Any] = {
        "supplier_id": "SUP-NC-882",
        "clause_category": "LIABILITY_CAP",
    }

    results = await opensearch_client.search_knn(
        index_name="contracts-v1",
        query_vector=query_vector,
        k=5,
        filter_criteria=filter_criteria,
    )

    assert len(results) == 1
    search_body = mock_opensearch_py_client.search.call_args[1]["body"]
    query = search_body["query"]

    # Must be structured as bool query with filter clauses and knn query
    assert "bool" in query
    assert "filter" in query["bool"]
    filters = query["bool"]["filter"]
    assert len(filters) == 2

    # Check terms inside filter
    filter_terms = {list(f["term"].keys())[0]: list(f["term"].values())[0] for f in filters}
    assert filter_terms["supplier_id"] == "SUP-NC-882"
    assert filter_terms["clause_category"] == "LIABILITY_CAP"


@pytest.mark.asyncio
async def test_document_retrieval_and_deletion(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify get_document and delete_document behave properly including not-found cases."""
    # Get document - Found
    mock_opensearch_py_client.get.return_value = {
        "_id": "doc-101",
        "_source": {"title": "Sample Contract Clause"},
    }
    doc = await opensearch_client.get_document("contracts-v1", "doc-101")
    assert doc is not None
    assert doc["title"] == "Sample Contract Clause"

    # Get document - Not found
    mock_opensearch_py_client.get.side_effect = NotFoundError(404, "Not Found")
    missing_doc = await opensearch_client.get_document("contracts-v1", "missing-id")
    assert missing_doc is None

    # Delete document - Success
    mock_opensearch_py_client.delete.side_effect = None
    mock_opensearch_py_client.delete.return_value = {"result": "deleted"}
    deleted = await opensearch_client.delete_document("contracts-v1", "doc-101")
    assert deleted is True

    # Delete document - Not found
    mock_opensearch_py_client.delete.side_effect = NotFoundError(404, "Not Found")
    deleted_missing = await opensearch_client.delete_document("contracts-v1", "missing-id")
    assert deleted_missing is False


@pytest.mark.asyncio
async def test_client_resilience_and_timeout_handling(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify cluster connection error and timeouts are caught and reported cleanly."""
    mock_opensearch_py_client.search.side_effect = ConnectionError("500", "Connection refused", {})

    with pytest.raises(ConnectionError, match="Connection refused"):
        await opensearch_client.search_knn(
            index_name="contracts-v1",
            query_vector=[0.1] * 1536,
            k=5,
        )


@pytest.mark.asyncio
async def test_client_close(
    opensearch_client: OpenSearchClient,
    mock_opensearch_py_client: AsyncMock,
) -> None:
    """Verify client close properly releases underlying HTTP connection pools."""
    await opensearch_client.close()
    mock_opensearch_py_client.close.assert_called_once()
