"""Implicit preference store — ChromaDB vector storage for learned preferences.

Stores observations like "张三把空调从25调到23" as embeddings so the Agent
can semantically retrieve relevant past behaviours during decision-making.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ImplicitStore:
    """Vector store backed by a ChromaDB collection ``implicit_preferences``."""

    COLLECTION_NAME = "implicit_preferences"

    def __init__(self, chroma_client: Any | None = None):
        self._client = chroma_client
        self._collection: Any | None = None
        if chroma_client is not None:
            try:
                self._collection = chroma_client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                )
                logger.info(
                    "ImplicitStore collection '%s' ready", self.COLLECTION_NAME
                )
            except Exception:
                logger.warning(
                    "Failed to init ImplicitStore collection", exc_info=True
                )

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Add a text document with metadata. Returns the document id."""
        if not self.available:
            logger.debug("ImplicitStore unavailable, skipping add")
            return None
        try:
            doc_id = uuid.uuid4().hex
            meta = dict(metadata or {})
            meta.setdefault("timestamp", datetime.now().isoformat())
            # ChromaDB metadata values must be str/int/float/bool
            meta = {k: str(v) if not isinstance(v, (int, float, bool)) else v for k, v in meta.items()}
            self._collection.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[meta],
            )
            return doc_id
        except Exception:
            logger.exception("ImplicitStore.add failed")
            return None

    def query(
        self,
        query_text: str,
        employee_id: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional employee_id filter."""
        if not self.available:
            return []
        try:
            where = {"employee_id": employee_id} if employee_id else None
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
                    "source": "implicit",
                }
                for doc, meta, dist in zip(docs, metas, distances)
            ]
        except Exception:
            logger.debug("ImplicitStore.query failed", exc_info=True)
            return []
