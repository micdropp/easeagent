"""Context memory — ChromaDB vector storage for scene-bound preferences.

Unlike ImplicitStore which captures raw behavioural observations, ContextMemory
stores preferences tied to specific scenarios (meeting, solo-work, break, etc.)
so the Agent can retrieve situation-appropriate settings.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ContextMemory:
    """Vector store backed by a ChromaDB collection ``context_memories``."""

    COLLECTION_NAME = "context_memories"

    def __init__(self, chroma_client: Any | None = None):
        self._client = chroma_client
        self._collection: Any | None = None
        if chroma_client is not None:
            try:
                self._collection = chroma_client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                )
                logger.info(
                    "ContextMemory collection '%s' ready", self.COLLECTION_NAME
                )
            except Exception:
                logger.warning(
                    "Failed to init ContextMemory collection", exc_info=True
                )

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Add a context-bound memory. Returns the document id."""
        if not self.available:
            logger.debug("ContextMemory unavailable, skipping add")
            return None
        try:
            doc_id = uuid.uuid4().hex
            meta = dict(metadata or {})
            meta.setdefault("timestamp", datetime.now().isoformat())
            meta = {k: str(v) if not isinstance(v, (int, float, bool)) else v for k, v in meta.items()}
            self._collection.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[meta],
            )
            return doc_id
        except Exception:
            logger.exception("ContextMemory.add failed")
            return None

    def query(
        self,
        query_text: str,
        employee_id: str | None = None,
        scene_type: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional employee_id and scene_type filter."""
        if not self.available:
            return []
        try:
            where_conditions: list[dict[str, Any]] = []
            if employee_id:
                where_conditions.append({"employee_id": employee_id})
            if scene_type:
                where_conditions.append({"scene_type": scene_type})

            where: dict[str, Any] | None = None
            if len(where_conditions) == 1:
                where = where_conditions[0]
            elif len(where_conditions) > 1:
                where = {"$and": where_conditions}

            results = self._collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where,
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return [
                {
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                    "source": "context",
                }
                for doc, meta, dist in zip(docs, metas, distances)
            ]
        except Exception:
            logger.debug("ContextMemory.query failed", exc_info=True)
            return []
