"""Amazon OpenSearch k-NN vector search client for ApexMotion platform.

Supports:
- k-NN vector index provisioning with HNSW cosine similarity mappings (LLD Section 3.2).
- Contract clause and risk intelligence document embedding upsert and bulk indexing.
- Exact and filtered nearest-neighbour vector search.
"""

from typing import Any

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import NotFoundError

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("apexmotion.database.opensearch")


class OpenSearchClient:
    """Asynchronous client for Amazon OpenSearch Service k-NN vector operations."""

    def __init__(
        self,
        endpoint: str | None = None,
        client: AsyncOpenSearch | None = None,
    ) -> None:
        settings = get_settings()
        self.endpoint = endpoint or settings.OPENSEARCH_ENDPOINT

        if client is not None:
            self.client = client
        else:
            self.client = AsyncOpenSearch(
                hosts=[self.endpoint],
                verify_certs=False,
                ssl_show_warn=False,
            )

    async def create_knn_index(
        self,
        index_name: str,
        dimension: int = 1536,
        space_type: str = "cosinesimil",
        ef_construction: int = 256,
        m: int = 16,
    ) -> bool:
        """Provision a k-NN vector index matching LLD Section 3.2 specification.

        Args:
            index_name: Name of target index (e.g. contracts-v1, news-v1).
            dimension: Embedding vector dimensions (default 1536 for Titan/OpenAI embeddings).
            space_type: Distance metric (cosinesimil, l2, innerproduct).
            ef_construction: HNSW graph construction exploration factor.
            m: Max number of bidirectional links per node in HNSW graph.

        Returns:
            True if created, False if index already exists.
        """
        exists = await self.client.indices.exists(index=index_name)
        if exists:
            logger.info("OpenSearch index already exists: %s", index_name)
            return False

        mapping = {
            "settings": {
                "index": {
                    "knn": True,
                    "number_of_shards": 3,
                    "number_of_replicas": 2,
                }
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "contract_id": {"type": "keyword"},
                    "supplier_id": {"type": "keyword"},
                    "clause_category": {"type": "keyword"},
                    "text_content": {"type": "text", "analyzer": "standard"},
                    "embedding_vector": {
                        "type": "knn_vector",
                        "dimension": dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": space_type,
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": ef_construction,
                                "m": m,
                            },
                        },
                    },
                    "page_number": {"type": "integer"},
                    "section_reference": {"type": "keyword"},
                }
            },
        }

        await self.client.indices.create(index=index_name, body=mapping)
        logger.info("Successfully provisioned k-NN vector index: %s", index_name)
        return True

    async def index_exists(self, index_name: str) -> bool:
        """Check whether an index exists in the OpenSearch cluster."""
        return bool(await self.client.indices.exists(index=index_name))

    async def delete_index(self, index_name: str) -> bool:
        """Delete an index if it exists."""
        if await self.index_exists(index_name):
            await self.client.indices.delete(index=index_name)
            logger.info("Deleted OpenSearch index: %s", index_name)
            return True
        return False

    async def upsert_document(
        self,
        index_name: str,
        doc_id: str,
        document: dict[str, Any],
        vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """Index or update a document with an optional embedding vector."""
        body = dict(document)
        if vector is not None:
            body["embedding_vector"] = vector

        res: dict[str, Any] = await self.client.index(
            index=index_name,
            id=doc_id,
            body=body,
            refresh=True,
        )
        return res

    async def bulk_upsert(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bulk index multiple documents into target index.

        Each item in documents should contain either 'id' or 'chunk_id',
        plus optional 'vector' which will be mapped to 'embedding_vector'.
        """
        actions: list[dict[str, Any]] = []
        for doc in documents:
            doc_id = doc.get("id") or doc.get("chunk_id")
            source = {k: v for k, v in doc.items() if k not in ("id", "chunk_id", "vector")}
            if "vector" in doc:
                source["embedding_vector"] = doc["vector"]

            action_meta: dict[str, Any] = {"_index": index_name}
            if doc_id is not None:
                action_meta["_id"] = str(doc_id)

            actions.append({"index": action_meta})
            actions.append(source)

        res: dict[str, Any] = await self.client.bulk(body=actions, refresh=True)
        return res

    async def search_knn(
        self,
        index_name: str,
        query_vector: list[float],
        k: int = 5,
        filter_criteria: dict[str, Any] | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """Perform k-nearest-neighbour vector similarity search.

        Args:
            index_name: Target OpenSearch index.
            query_vector: Dense floating-point embedding vector.
            k: Top-k nearest neighbours to retrieve.
            filter_criteria: Optional dictionary of keyword metadata filters.
            min_score: Minimum cosine similarity score threshold.

        Returns:
            List of parsed hits with id, score, and document source payload.
        """
        knn_clause = {
            "knn": {
                "embedding_vector": {
                    "vector": query_vector,
                    "k": k,
                }
            }
        }

        body: dict[str, Any] = {"size": k}

        if filter_criteria:
            filters = [{"term": {field: val}} for field, val in filter_criteria.items()]
            body["query"] = {
                "bool": {
                    "filter": filters,
                    "must": [knn_clause],
                }
            }
        else:
            body["query"] = knn_clause

        if min_score is not None:
            body["min_score"] = min_score

        response = await self.client.search(index=index_name, body=body)
        raw_hits = response.get("hits", {}).get("hits", [])

        results: list[dict[str, Any]] = []
        for hit in raw_hits:
            results.append(
                {
                    "id": hit.get("_id"),
                    "score": hit.get("_score"),
                    "document": hit.get("_source", {}),
                }
            )

        return results

    async def get_document(self, index_name: str, doc_id: str) -> dict[str, Any] | None:
        """Fetch document source by ID; returns None if not found."""
        try:
            res = await self.client.get(index=index_name, id=doc_id)
            source: dict[str, Any] = res.get("_source", {})
            return source
        except NotFoundError:
            return None

    async def delete_document(self, index_name: str, doc_id: str) -> bool:
        """Delete a document by ID; returns True if deleted, False if not found."""
        try:
            await self.client.delete(index=index_name, id=doc_id)
            return True
        except NotFoundError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.close()
