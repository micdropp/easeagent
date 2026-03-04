"""Explicit preference store — thin wrapper around SQLite Preference model."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, and_

from core.models import Preference

logger = logging.getLogger(__name__)


class ExplicitStore:
    """CRUD operations on the SQLite ``preferences`` table."""

    def __init__(self, db_session_factory: Any):
        self._db_factory = db_session_factory

    async def get_preferences(
        self,
        employee_id: str,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            async with self._db_factory() as session:
                conditions = [Preference.employee_id == employee_id]
                if context:
                    conditions.append(Preference.context == context)
                stmt = select(Preference).where(and_(*conditions))
                rows = await session.execute(stmt)
                return [
                    {
                        "category": p.category,
                        "key": p.key,
                        "value": p.value,
                        "context": p.context,
                        "source": "explicit",
                    }
                    for p in rows.scalars().all()
                ]
        except Exception:
            logger.debug("Failed to load explicit preferences", exc_info=True)
            return []

    async def set_preference(
        self,
        employee_id: str,
        category: str,
        key: str,
        value: str,
        context: str | None = None,
    ) -> None:
        try:
            async with self._db_factory() as session:
                conditions = [
                    Preference.employee_id == employee_id,
                    Preference.category == category,
                    Preference.key == key,
                ]
                if context:
                    conditions.append(Preference.context == context)

                stmt = select(Preference).where(and_(*conditions))
                row = await session.execute(stmt)
                existing = row.scalars().first()

                if existing:
                    existing.value = value
                else:
                    session.add(
                        Preference(
                            employee_id=employee_id,
                            category=category,
                            key=key,
                            value=value,
                            context=context,
                        )
                    )
                await session.commit()
        except Exception:
            logger.exception("Failed to set explicit preference")

    async def get_all_for_employees(
        self, employee_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Batch-fetch preferences for multiple employees."""
        if not employee_ids:
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        try:
            async with self._db_factory() as session:
                stmt = select(Preference).where(
                    Preference.employee_id.in_(employee_ids)
                )
                rows = await session.execute(stmt)
                for p in rows.scalars().all():
                    result.setdefault(p.employee_id, []).append(
                        {
                            "category": p.category,
                            "key": p.key,
                            "value": p.value,
                            "context": p.context,
                            "source": "explicit",
                        }
                    )
        except Exception:
            logger.debug("Failed to batch-load preferences", exc_info=True)
        return result
