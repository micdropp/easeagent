"""Dynamic multimodal prompt builder for the EaseAgent cognitive layer.

Assembles system prompt + scene image + sensor data + occupant info +
device states + employee preferences into a single message list that
can be sent to any multimodal LLM.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime
from typing import Any

import cv2
import numpy as np

from core.config import load_agent_prompt
from core.event_bus import Event

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds multimodal prompts from event context + live data sources."""

    def __init__(
        self,
        perception_pipeline: Any | None,
        sensor_collector: Any | None,
        device_registry: Any,
        db_session_factory: Any,
        conflict_resolver: Any | None = None,
        rag_retriever: Any | None = None,
    ):
        self._perception = perception_pipeline
        self._sensor = sensor_collector
        self._devices = device_registry
        self._db_factory = db_session_factory
        self._conflict = conflict_resolver
        self._rag = rag_retriever
        self._system_prompt = load_agent_prompt()

    async def build(
        self,
        event: Event,
        frame: np.ndarray | None = None,
    ) -> list[dict[str, Any]]:
        """Build a full multimodal prompt for the given event.

        Returns a list of message dicts ready for ``LLMClient.chat()``.
        """
        messages: list[dict[str, Any]] = []

        messages.append({"role": "system", "content": self._system_prompt})

        room_id = event.room_id or event.data.get("room_id", "unknown")

        occupants = self._get_occupants(room_id)
        sensor_snapshot = self._get_sensor(room_id)
        device_states = self._get_device_states(room_id)
        preferences = await self._get_preferences(occupants)
        compromise = self._get_compromise(preferences) if len(occupants) > 1 else None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text_parts = [
            f"当前时间: {now_str}",
            f"事件类型: {event.type}",
            f"房间: {room_id}",
        ]

        if occupants:
            names = ", ".join(
                f"{o.get('employee_id', '?')}(置信度{o.get('confidence', 0):.0%})"
                for o in occupants
            )
            text_parts.append(f"在场人员: {names}")
        else:
            text_parts.append("在场人员: 无 (可能有未识别的人)")

        if sensor_snapshot:
            parts = []
            if "temperature" in sensor_snapshot:
                parts.append(f"温度 {sensor_snapshot['temperature']}°C")
            if "humidity" in sensor_snapshot:
                parts.append(f"湿度 {sensor_snapshot['humidity']}%")
            if "co2" in sensor_snapshot:
                parts.append(f"CO2 {sensor_snapshot['co2']}ppm")
            if parts:
                text_parts.append(f"传感器: {', '.join(parts)}")

        if device_states:
            dev_desc = []
            for dev in device_states:
                state_str = ", ".join(
                    f"{k}={v}" for k, v in dev.get("state", {}).items()
                ) or "无状态"
                online = "在线" if dev.get("is_online") else "离线"
                dev_desc.append(
                    f"  {dev['device_id']}({dev['device_type']}, {online}): {state_str}"
                )
            text_parts.append("设备状态:\n" + "\n".join(dev_desc))

        if preferences:
            pref_desc = []
            for emp_id, prefs in preferences.items():
                explicit = [p for p in prefs if p.get("source") != "implicit" and p.get("category") not in ("implicit", "context")]
                implicit = [p for p in prefs if p.get("category") == "implicit"]
                context_mems = [p for p in prefs if p.get("category") == "context"]

                parts_for_emp: list[str] = []
                if explicit:
                    parts_for_emp.append(
                        "[显式] " + ", ".join(f"{p['key']}={p['value']}" for p in explicit)
                    )
                if implicit:
                    parts_for_emp.append(
                        "[学习] " + "; ".join(p["value"] for p in implicit)
                    )
                if context_mems:
                    parts_for_emp.append(
                        "[情境] " + "; ".join(p["value"] for p in context_mems)
                    )
                if parts_for_emp:
                    pref_desc.append(f"  {emp_id}: {' | '.join(parts_for_emp)}")
                else:
                    items = ", ".join(f"{p['key']}={p['value']}" for p in prefs)
                    pref_desc.append(f"  {emp_id}: {items}")
            text_parts.append("员工偏好:\n" + "\n".join(pref_desc))

        if compromise:
            comp_desc = ", ".join(f"{k}={v}" for k, v in compromise.items())
            text_parts.append(f"多人偏好协调建议: {comp_desc}")

        if event.data:
            extra = {
                k: v
                for k, v in event.data.items()
                if k not in ("room_id", "frame_base64")
            }
            if extra:
                text_parts.append(f"事件详情: {extra}")

        text_parts.append(
            "\n请观察画面，分析当前场景，决定是否需要调整办公环境。"
            "如果需要调整，请使用工具调用。如果环境已适宜，回复'当前环境适宜，无需调节'。"
        )

        text_content = "\n".join(text_parts)

        if frame is not None:
            img_b64 = self._encode_frame(frame)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img_b64},
                        {"type": "text", "text": text_content},
                    ],
                }
            )
        else:
            frame_b64 = event.data.get("frame_base64")
            if frame_b64:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": frame_b64},
                            {"type": "text", "text": text_content},
                        ],
                    }
                )
            else:
                messages.append({"role": "user", "content": text_content})

        return messages

    # ------------------------------------------------------------------
    # Data collection helpers
    # ------------------------------------------------------------------

    def _get_occupants(self, room_id: str) -> list[dict[str, Any]]:
        if self._perception is None:
            return []
        try:
            return self._perception.get_room_occupants(room_id)
        except Exception:
            return []

    def _get_sensor(self, room_id: str) -> dict[str, Any]:
        if self._sensor is None:
            return {}
        try:
            return self._sensor.get_latest(room_id) or {}
        except Exception:
            return {}

    def _get_device_states(self, room_id: str) -> list[dict[str, Any]]:
        try:
            devices = self._devices.get_room_devices(room_id)
            return [
                {
                    "device_id": d.device_id,
                    "device_type": d.device_type,
                    "is_online": d.is_online,
                    "state": d.state,
                }
                for d in devices
            ]
        except Exception:
            return []

    async def _get_preferences(
        self, occupants: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch preferences for all present employees via RAG retriever.

        Falls back to direct SQLite query if RAGRetriever is unavailable.
        """
        if not occupants:
            return {}

        employee_ids = [
            occ.get("employee_id") for occ in occupants if occ.get("employee_id")
        ]
        if not employee_ids:
            return {}

        if self._rag is not None:
            return await self._get_preferences_via_rag(employee_ids)

        return await self._get_preferences_fallback(employee_ids)

    async def _get_preferences_via_rag(
        self, employee_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Use RAGRetriever to get three-tier merged preferences."""
        result: dict[str, list[dict[str, Any]]] = {}
        try:
            profiles = await self._rag.retrieve_many(employee_ids)
            for emp_id, profile in profiles.items():
                items: list[dict[str, Any]] = []
                for p in profile.get("explicit", []):
                    items.append(p)
                for m in profile.get("implicit", [])[:3]:
                    items.append({
                        "category": "implicit",
                        "key": "learned",
                        "value": m["text"],
                        "context": m.get("metadata", {}).get("scene_type"),
                    })
                for m in profile.get("context", [])[:3]:
                    items.append({
                        "category": "context",
                        "key": "memory",
                        "value": m["text"],
                        "context": m.get("metadata", {}).get("scene_type"),
                    })
                if items:
                    result[emp_id] = items
        except Exception:
            logger.debug("RAG retrieval failed, falling back", exc_info=True)
            result = await self._get_preferences_fallback(employee_ids)
        return result

    async def _get_preferences_fallback(
        self, employee_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Direct SQLite query as fallback when RAGRetriever is unavailable."""
        from sqlalchemy import select
        from core.models import Preference

        result: dict[str, list[dict[str, Any]]] = {}
        try:
            async with self._db_factory() as session:
                for emp_id in employee_ids:
                    stmt = select(Preference).where(
                        Preference.employee_id == emp_id
                    )
                    rows = await session.execute(stmt)
                    prefs = rows.scalars().all()
                    if prefs:
                        result[emp_id] = [
                            {
                                "category": p.category,
                                "key": p.key,
                                "value": p.value,
                                "context": p.context,
                            }
                            for p in prefs
                        ]
        except Exception:
            logger.debug("Failed to load preferences", exc_info=True)
        return result

    def _get_compromise(
        self, preferences: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any] | None:
        if self._conflict is None:
            return None
        try:
            return self._conflict.resolve(preferences)
        except Exception:
            return None

    @staticmethod
    def _encode_frame(frame: np.ndarray, quality: int = 70) -> str:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf).decode()
