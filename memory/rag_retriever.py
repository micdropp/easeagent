"""RAG retriever — unified search across all three memory tiers.

Combines explicit SQLite preferences, implicit ChromaDB preferences and
context-bound ChromaDB memories into a single ranked result set that
can be injected into the Agent's prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from memory.explicit_store import ExplicitStore
from memory.implicit_store import ImplicitStore
from memory.context_memory import ContextMemory

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieves and merges memory from all three tiers for prompt injection."""

    def __init__(
        self,
        explicit: ExplicitStore,
        implicit: ImplicitStore,
        context: ContextMemory,
    ):
        self._explicit = explicit
        self._implicit = implicit
        self._context = context

    async def retrieve(
        self,
        employee_id: str,
        context_hint: str | None = None,
        n_results: int = 5,
    ) -> dict[str, Any]:
        """Return a structured preference profile for one employee.

        Returns
        -------
        dict with keys:
            - explicit: list of explicit preferences
            - implicit: list of implicit (learned) preferences
            - context: list of context-bound memories
            - summary: formatted text ready for prompt injection
        """
        explicit = await self._explicit.get_preferences(employee_id)

        query_text = f"{employee_id} {context_hint or '办公'} 偏好设置"
        implicit = self._implicit.query(
            query_text=query_text,
            employee_id=employee_id,
            n_results=n_results,
        )
        ctx_memories = self._context.query(
            query_text=query_text,
            employee_id=employee_id,
            n_results=n_results,
        )

        summary = self._format_summary(employee_id, explicit, implicit, ctx_memories)

        return {
            "explicit": explicit,
            "implicit": implicit,
            "context": ctx_memories,
            "summary": summary,
        }

    async def retrieve_many(
        self,
        employee_ids: list[str],
        context_hint: str | None = None,
        n_results: int = 3,
    ) -> dict[str, dict[str, Any]]:
        """Retrieve profiles for multiple employees at once."""
        result: dict[str, dict[str, Any]] = {}
        for emp_id in employee_ids:
            result[emp_id] = await self.retrieve(emp_id, context_hint, n_results)
        return result

    @staticmethod
    def _format_summary(
        employee_id: str,
        explicit: list[dict[str, Any]],
        implicit: list[dict[str, Any]],
        ctx_memories: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []

        if explicit:
            items = [f"{p['key']}={p['value']}" for p in explicit]
            parts.append(f"[显式偏好] {', '.join(items)}")

        if implicit:
            items = [m["text"] for m in implicit[:3]]
            parts.append(f"[学习偏好] {'; '.join(items)}")

        if ctx_memories:
            items = [m["text"] for m in ctx_memories[:3]]
            parts.append(f"[情境记忆] {'; '.join(items)}")

        if not parts:
            return f"{employee_id}: 暂无偏好记录"

        return f"{employee_id}: " + " | ".join(parts)
