"""Multi-person preference conflict resolver.

When multiple employees occupy a room, their individual preferences may
conflict (e.g. one prefers 22 deg C while another prefers 26 deg C).
This module calculates a compromise and provides it as context for the
LLM to make a final decision.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NUMERIC_KEYS = {
    "temperature": float,
    "brightness": int,
    "color_temp": int,
}

PRIORITY_KEYS = {
    "fresh_air": ["max", "high", "medium", "low", "off"],
}


class ConflictResolver:
    """Resolves preference conflicts among multiple occupants."""

    def resolve(
        self, preferences: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        """Return a compromise dict from per-employee preference lists.

        ``preferences`` maps ``employee_id`` to a list of preference
        dicts, each with ``category``, ``key``, ``value``, ``context``.
        """
        if len(preferences) <= 1:
            return {}

        aggregated: dict[str, list[str]] = {}
        for _emp_id, pref_list in preferences.items():
            for p in pref_list:
                key = p.get("key", "")
                val = p.get("value", "")
                if key and val:
                    aggregated.setdefault(key, []).append(val)

        result: dict[str, Any] = {}

        for key, values in aggregated.items():
            if key in NUMERIC_KEYS:
                compromise = self._average_numeric(values, NUMERIC_KEYS[key])
                if compromise is not None:
                    result[key] = compromise
            elif key in PRIORITY_KEYS:
                compromise = self._highest_priority(values, PRIORITY_KEYS[key])
                if compromise is not None:
                    result[key] = compromise

        if result:
            logger.info(
                "Conflict resolved for %d employees: %s",
                len(preferences),
                result,
            )
        return result

    @staticmethod
    def _average_numeric(
        values: list[str], cast_fn: type
    ) -> int | float | None:
        nums = []
        for v in values:
            try:
                nums.append(cast_fn(v))
            except (ValueError, TypeError):
                continue
        if not nums:
            return None
        avg = sum(nums) / len(nums)
        return cast_fn(round(avg)) if cast_fn is int else round(avg, 1)

    @staticmethod
    def _highest_priority(
        values: list[str], priority_order: list[str]
    ) -> str | None:
        """Return the value with the highest priority (lowest index wins)."""
        best_idx = len(priority_order)
        best_val = None
        for v in values:
            v_lower = v.lower().strip()
            if v_lower in priority_order:
                idx = priority_order.index(v_lower)
                if idx < best_idx:
                    best_idx = idx
                    best_val = v_lower
        return best_val
