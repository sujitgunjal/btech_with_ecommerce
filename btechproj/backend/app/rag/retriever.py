"""Semantic retriever for historical incidents using ChromaDB."""

import logging
from typing import Any

from ..config import get_settings
from .embeddings import EmbeddingService
from .vector_store import VectorStore

logger = logging.getLogger("incident-backend")


class IncidentRetriever:
    """Retrieves similar historical incidents using semantic search.

    Embeds a text query with Sentence Transformers and searches the
    ChromaDB vector store for the closest historical incidents.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._embedding_service = EmbeddingService(
            model_name=settings.EMBEDDING_MODEL
        )
        self._vector_store = VectorStore()
        self._top_k = settings.RAG_TOP_K

    def retrieve(
        self, query: str, top_k: int | None = None
    ) -> list[dict[str, Any]]:
        """Embed *query* and return the top-k similar historical incidents.

        Each result dict contains:
            incident_id, document, metadata, distance, similarity_score
        """
        k = top_k or self._top_k
        query_embedding = self._embedding_service.embed_text(query)

        raw = self._vector_store.search(query_embedding, top_k=k)

        results: list[dict[str, Any]] = []
        ids = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]

        for i, (iid, dist, doc, meta) in enumerate(
            zip(ids, distances, documents, metadatas)
        ):
            similarity = 1.0 / (1.0 + dist)
            results.append(
                {
                    "incident_id": iid,
                    "document": doc,
                    "metadata": meta or {},
                    "distance": dist,
                    "similarity_score": round(similarity, 4),
                }
            )

        logger.info(
            "Retrieved %d historical incidents (top_k=%d) — ids=%s",
            len(results),
            k,
            [r["incident_id"] for r in results],
        )
        return results
