"""Preference learner — extracts implicit preferences from Agent behaviour.

When an employee manually overrides an Agent decision (e.g. changes the
temperature from 25 to 23), the learner records this as an implicit
preference so the Agent can do better next time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from memory.implicit_store import ImplicitStore
from memory.context_memory import ContextMemory

logger = logging.getLogger(__name__)


class PreferenceLearner:
    """Learns employee preferences from decision outcomes."""

    def __init__(
        self,
        implicit: ImplicitStore,
        context: ContextMemory,
    ):
        self._implicit = implicit
        self._context = context

    def learn_from_override(
        self,
        employee_id: str,
        device_type: str,
        agent_value: str,
        user_value: str,
        context: str | None = None,
    ) -> None:
        """Record when a user manually changed an Agent-set value."""
        memory_text = (
            f"{employee_id}在{context or '办公'}情境下，"
            f"将{device_type}从{agent_value}改为{user_value}，"
            f"说明其偏好为{user_value}"
        )
        metadata = {
            "employee_id": employee_id,
            "device_type": device_type,
            "agent_value": agent_value,
            "user_value": user_value,
            "learn_type": "override",
            "timestamp": datetime.now().isoformat(),
        }

        self._implicit.add(text=memory_text, metadata=metadata)

        if context:
            ctx_text = (
                f"{employee_id}{context}时偏好{device_type}={user_value}"
            )
            ctx_metadata = {
                **metadata,
                "scene_type": context,
            }
            self._context.add(text=ctx_text, metadata=ctx_metadata)

        logger.info(
            "Learned preference: %s prefers %s=%s (was %s) in context '%s'",
            employee_id,
            device_type,
            user_value,
            agent_value,
            context or "general",
        )

    def learn_from_decision(
        self,
        decision_data: dict[str, Any],
    ) -> None:
        """Extract learnable information from a completed decision cycle.

        Currently records successful tool-call patterns per employee so the
        Agent can recall what it did last time in a similar situation.
        """
        tool_calls_raw = decision_data.get("tool_calls")
        if not tool_calls_raw:
            return

        if isinstance(tool_calls_raw, str):
            try:
                tool_calls = json.loads(tool_calls_raw)
            except (json.JSONDecodeError, TypeError):
                return
        else:
            tool_calls = tool_calls_raw

        if not tool_calls:
            return

        room_id = decision_data.get("room_id", "unknown")
        trigger = decision_data.get("trigger_event", "unknown")
        detected = decision_data.get("detected_people")
        if isinstance(detected, str):
            try:
                detected = json.loads(detected)
            except (json.JSONDecodeError, TypeError):
                detected = []

        employee_ids = [e for e in (detected or []) if e]
        if not employee_ids:
            return

        action_parts = []
        for tc in tool_calls:
            name = tc.get("name", "?")
            args = tc.get("arguments", {})
            action_parts.append(f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})")
        action_summary = "; ".join(action_parts)

        for emp_id in employee_ids:
            memory_text = (
                f"当{emp_id}在{room_id}触发{trigger}时，"
                f"Agent执行了: {action_summary}"
            )
            self._context.add(
                text=memory_text,
                metadata={
                    "employee_id": emp_id,
                    "room_id": room_id,
                    "trigger_event": trigger,
                    "scene_type": trigger,
                    "learn_type": "decision_trace",
                    "timestamp": datetime.now().isoformat(),
                },
            )
