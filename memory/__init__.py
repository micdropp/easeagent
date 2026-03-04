"""EaseAgent Memory Layer — three-tier memory system.

Tier 1: Explicit preferences (SQLite)
Tier 2: Implicit preferences (ChromaDB vectors)
Tier 3: Context memories (ChromaDB vectors, scene-bound)
"""

from __future__ import annotations

from typing import Any

from memory.explicit_store import ExplicitStore
from memory.implicit_store import ImplicitStore
from memory.context_memory import ContextMemory
from memory.rag_retriever import RAGRetriever
from memory.preference_learner import PreferenceLearner


class MemorySystem:
    """Aggregates all memory sub-systems into a single facade."""

    def __init__(
        self,
        db_session_factory: Any,
        chroma_client: Any | None = None,
    ):
        self.explicit = ExplicitStore(db_session_factory)
        self.implicit = ImplicitStore(chroma_client)
        self.context = ContextMemory(chroma_client)
        self.retriever = RAGRetriever(
            explicit=self.explicit,
            implicit=self.implicit,
            context=self.context,
        )
        self.learner = PreferenceLearner(
            implicit=self.implicit,
            context=self.context,
        )
