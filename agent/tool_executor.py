"""Tool executor — bridges LLM function-call output to real device operations."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.llm_client import ToolCall

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Routes LLM tool calls to actual handlers (MQTT publish, DB query, etc.).

    Each handler receives keyword arguments parsed from the LLM's
    ``arguments`` dict and returns a JSON-serialisable result dict.
    """

    def __init__(
        self,
        mqtt_client: Any,
        device_registry: Any,
        db_session_factory: Any,
        redis_client: Any | None = None,
        implicit_store: Any | None = None,
        feishu_bot: Any | None = None,
    ):
        self._mqtt = mqtt_client
        self._devices = device_registry
        self._db_factory = db_session_factory
        self._redis = redis_client
        self._implicit_store = implicit_store
        self._feishu = feishu_bot

        self._handlers: dict[str, Any] = {
            "control_light": self._handle_light,
            "control_curtain": self._handle_curtain,
            "control_ac": self._handle_ac,
            "control_screen": self._handle_screen,
            "control_fresh_air": self._handle_fresh_air,
            "get_employee_preference": self._handle_get_preference,
            "notify_feishu": self._handle_notify,
            "update_preference_memory": self._handle_update_memory,
        }

    async def execute(self, tool_call: ToolCall) -> dict[str, Any]:
        """Execute a single tool call and return the result dict."""
        handler = self._handlers.get(tool_call.name)
        if not handler:
            logger.warning("Unknown tool: %s", tool_call.name)
            return {"status": "error", "message": f"未知工具: {tool_call.name}"}

        try:
            result = await handler(**tool_call.arguments)
            logger.info(
                "Tool '%s' executed successfully: %s",
                tool_call.name,
                json.dumps(result, ensure_ascii=False)[:200],
            )
            return {"status": "success", "result": result}
        except Exception as exc:
            logger.exception("Tool '%s' execution failed", tool_call.name)
            return {"status": "error", "message": str(exc)}

    async def execute_many(self, tool_calls: list[ToolCall]) -> list[dict[str, Any]]:
        """Execute a list of tool calls sequentially."""
        results = []
        for tc in tool_calls:
            r = await self.execute(tc)
            results.append(r)
        return results

    # ------------------------------------------------------------------
    # Device control handlers
    # ------------------------------------------------------------------

    async def _handle_light(
        self,
        room_id: str,
        action: str,
        brightness: int | None = None,
        color_temp: int | None = None,
        device_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action}
        if brightness is not None:
            payload["brightness"] = brightness
        if color_temp is not None:
            payload["color_temp"] = color_temp

        if device_id:
            topic = f"easeagent/{room_id}/light/{device_id}/cmd"
            await self._mqtt.publish(topic, payload)
            await self._devices.update_state(device_id, payload)
            return {"device": device_id, "action": action, **payload}

        devices = self._devices.get_room_devices(room_id, "light")
        controlled = []
        for dev in devices:
            topic = f"easeagent/{room_id}/light/{dev.device_id}/cmd"
            await self._mqtt.publish(topic, payload)
            await self._devices.update_state(dev.device_id, payload)
            controlled.append(dev.device_id)
        return {"room_id": room_id, "action": action, "devices": controlled, **payload}

    async def _handle_curtain(
        self,
        room_id: str,
        action: str,
        position: int | None = None,
        device_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action}
        if position is not None:
            payload["position"] = position

        if device_id:
            topic = f"easeagent/{room_id}/curtain/{device_id}/cmd"
            await self._mqtt.publish(topic, payload)
            await self._devices.update_state(device_id, payload)
            return {"device": device_id, "action": action, **payload}

        devices = self._devices.get_room_devices(room_id, "curtain")
        controlled = []
        for dev in devices:
            topic = f"easeagent/{room_id}/curtain/{dev.device_id}/cmd"
            await self._mqtt.publish(topic, payload)
            await self._devices.update_state(dev.device_id, payload)
            controlled.append(dev.device_id)
        return {"room_id": room_id, "action": action, "devices": controlled, **payload}

    async def _handle_ac(
        self,
        room_id: str,
        action: str,
        temperature: float | None = None,
        mode: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action}
        if temperature is not None:
            payload["temperature"] = temperature
        if mode:
            payload["mode"] = mode

        device = self._devices.get(room_id, "ac")
        dev_id = device.device_id if device else f"ac_{room_id}"
        topic = f"easeagent/{room_id}/ac/{dev_id}/cmd"
        await self._mqtt.publish(topic, payload)
        if device:
            await self._devices.update_state(dev_id, payload)
        return {"device": dev_id, "action": action, **payload}

    async def _handle_screen(
        self,
        screen_id: str,
        content_type: str,
        message: str | None = None,
        target_employee: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content_type": content_type}
        if message:
            payload["message"] = message
        if target_employee:
            payload["target_employee"] = target_employee

        topic = f"easeagent/screen/{screen_id}/content"
        await self._mqtt.publish(topic, payload)
        return {"screen": screen_id, "content_type": content_type}

    async def _handle_fresh_air(
        self,
        level: str,
        reason: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"level": level}
        if reason:
            payload["reason"] = reason
        await self._mqtt.publish("easeagent/fresh_air/cmd", payload)
        return {"level": level, "reason": reason}

    # ------------------------------------------------------------------
    # Data query handlers
    # ------------------------------------------------------------------

    async def _handle_get_preference(
        self,
        employee_id: str,
        context: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        from sqlalchemy import select
        from core.models import Preference

        async with self._db_factory() as session:
            stmt = select(Preference).where(
                Preference.employee_id == employee_id
            )
            if context:
                stmt = stmt.where(Preference.context == context)
            result = await session.execute(stmt)
            prefs = result.scalars().all()

        pref_list = [
            {
                "category": p.category,
                "key": p.key,
                "value": p.value,
                "context": p.context,
            }
            for p in prefs
        ]
        return {"employee_id": employee_id, "preferences": pref_list}

    # ------------------------------------------------------------------
    # Notification — Feishu Bot (Phase 6)
    # ------------------------------------------------------------------

    async def _handle_notify(
        self,
        employee_id: str,
        message: str,
        msg_type: str = "text",
        **_: Any,
    ) -> dict[str, Any]:
        if self._feishu and self._feishu.available:
            return await self._feishu.notify(employee_id, message, msg_type)

        logger.info(
            "Feishu not configured, notify skipped: employee=%s msg=%s",
            employee_id,
            message[:100],
        )
        return {
            "notified": employee_id,
            "message": message,
            "sent": False,
            "note": "飞书未配置，请在 .env 中设置 FEISHU_APP_ID 等凭证",
        }

    # ------------------------------------------------------------------
    # Memory update — writes to ChromaDB implicit preference store
    # ------------------------------------------------------------------

    async def _handle_update_memory(
        self,
        employee_id: str,
        observation: str,
        context: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if self._implicit_store is not None and self._implicit_store.available:
            doc_id = self._implicit_store.add(
                text=observation,
                metadata={
                    "employee_id": employee_id,
                    "context": context or "general",
                    "learn_type": "llm_observation",
                },
            )
            logger.info(
                "Memory written to vector store: employee=%s doc=%s",
                employee_id,
                doc_id,
            )
            return {
                "updated": employee_id,
                "observation": observation,
                "stored": True,
                "doc_id": doc_id,
            }

        logger.info(
            "Memory update (no vector store): employee=%s observation=%s",
            employee_id,
            observation[:100],
        )
        return {
            "updated": employee_id,
            "observation": observation,
            "stored": False,
            "note": "ChromaDB 不可用，记忆未持久化",
        }
