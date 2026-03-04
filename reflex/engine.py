"""Reflex layer — fast, rule-based responses that bypass the LLM.

Handles deterministic actions such as turning off lights/AC after a room
is empty for N seconds, boosting ventilation when CO2 is high, and
updating toilet stall status from door sensors.  Each action publishes a
``reflex_action`` event so the cognitive layer stays informed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.config import load_rooms_config
from core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)


class ReflexEngine:
    """Subscribe to low-level perception events and react instantly."""

    def __init__(
        self,
        event_bus: EventBus,
        tool_executor: Any,
        mqtt_client: Any | None = None,
    ):
        self._bus = event_bus
        self._executor = tool_executor
        self._mqtt = mqtt_client

        self._room_rules: dict[str, dict[str, Any]] = {}
        self._room_devices: dict[str, dict[str, list[str]]] = {}
        self._vacancy_timers: dict[str, asyncio.Task] = {}
        self._room_person_count: dict[str, int] = {}
        self._running = False

        self._load_config()

    def _load_config(self) -> None:
        cfg = load_rooms_config()
        for room in cfg.get("rooms", []):
            rid = room["id"]
            rules = room.get("reflex_rules", {})
            if rules:
                self._room_rules[rid] = rules

            devs: dict[str, list[str]] = {}
            devices_block = room.get("devices", {})
            for dtype, ids in devices_block.items():
                if isinstance(ids, list):
                    devs[dtype] = ids
            self._room_devices[rid] = devs

        logger.info(
            "ReflexEngine loaded rules for %d rooms: %s",
            len(self._room_rules),
            list(self._room_rules.keys()),
        )

    def subscribe(self) -> None:
        self._bus.subscribe("person_left", self._on_person_left)
        self._bus.subscribe("person_entered", self._on_person_entered)
        self._bus.subscribe("co2_high", self._on_co2_high)
        self._bus.subscribe("toilet_sensor", self._on_toilet_sensor)
        self._running = True
        logger.info("ReflexEngine subscribed to events")

    async def stop(self) -> None:
        self._running = False
        for task in self._vacancy_timers.values():
            task.cancel()
        self._vacancy_timers.clear()
        logger.info("ReflexEngine stopped")

    # ------------------------------------------------------------------
    # person_left → start vacancy countdown
    # ------------------------------------------------------------------

    async def _on_person_left(self, event: Event) -> None:
        room_id = event.room_id or event.data.get("room_id", "")
        count = event.data.get("count", 0)
        self._room_person_count[room_id] = count

        if count > 0:
            return

        rules = self._room_rules.get(room_id)
        if not rules:
            return

        delay = rules.get("no_person_delay", 300)

        if room_id in self._vacancy_timers:
            self._vacancy_timers[room_id].cancel()

        self._vacancy_timers[room_id] = asyncio.create_task(
            self._vacancy_countdown(room_id, delay)
        )
        logger.info(
            "Reflex: room %s empty, vacancy timer started (%ds)", room_id, delay
        )

    async def _vacancy_countdown(self, room_id: str, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.debug("Reflex: vacancy timer cancelled for %s", room_id)
            return

        if self._room_person_count.get(room_id, 0) > 0:
            return

        logger.info("Reflex: room %s vacant for %ds, turning off devices", room_id, delay)
        await self._turn_off_room(room_id)

    async def _turn_off_room(self, room_id: str) -> None:
        from agent.llm_client import ToolCall

        actions_taken: list[dict[str, Any]] = []
        devs = self._room_devices.get(room_id, {})

        if devs.get("lights"):
            tc = ToolCall(
                id="reflex_light_off",
                name="control_light",
                arguments={"room_id": room_id, "action": "off"},
            )
            result = await self._executor.execute(tc)
            actions_taken.append({"tool": "control_light", "args": {"action": "off"}, "result": result})

        if devs.get("acs"):
            tc = ToolCall(
                id="reflex_ac_off",
                name="control_ac",
                arguments={"room_id": room_id, "action": "off"},
            )
            result = await self._executor.execute(tc)
            actions_taken.append({"tool": "control_ac", "args": {"action": "off"}, "result": result})

        if devs.get("screens"):
            for sid in devs["screens"]:
                tc = ToolCall(
                    id="reflex_screen_off",
                    name="control_screen",
                    arguments={"screen_id": sid, "content_type": "off"},
                )
                result = await self._executor.execute(tc)
                actions_taken.append({"tool": "control_screen", "args": {"screen_id": sid}, "result": result})

        await self._publish_reflex_action(
            room_id=room_id,
            reason="vacancy_timeout",
            actions=actions_taken,
            safety=False,
        )

    # ------------------------------------------------------------------
    # person_entered → cancel vacancy timer
    # ------------------------------------------------------------------

    async def _on_person_entered(self, event: Event) -> None:
        room_id = event.room_id or event.data.get("room_id", "")
        count = event.data.get("count", 0)
        self._room_person_count[room_id] = count

        timer = self._vacancy_timers.pop(room_id, None)
        if timer is not None:
            timer.cancel()
            logger.info("Reflex: person re-entered %s, vacancy timer cancelled", room_id)

    # ------------------------------------------------------------------
    # co2_high → immediately boost ventilation (safety action)
    # ------------------------------------------------------------------

    async def _on_co2_high(self, event: Event) -> None:
        room_id = event.room_id or event.data.get("room_id", "")
        co2 = event.data.get("co2_value", event.data.get("co2", 0))

        from agent.llm_client import ToolCall

        tc = ToolCall(
            id="reflex_fresh_air",
            name="control_fresh_air",
            arguments={"level": "high", "reason": f"CO2={co2}ppm 超标，反射层紧急加大新风"},
        )
        result = await self._executor.execute(tc)
        logger.warning("Reflex: CO2 high (%s ppm) in %s, fresh air set to HIGH", co2, room_id)

        await self._publish_reflex_action(
            room_id=room_id,
            reason="co2_high",
            actions=[{"tool": "control_fresh_air", "args": {"level": "high"}, "result": result}],
            safety=True,
        )

    # ------------------------------------------------------------------
    # toilet_sensor → update stall status
    # ------------------------------------------------------------------

    async def _on_toilet_sensor(self, event: Event) -> None:
        stall_id = event.data.get("stall_id", "")
        occupied = event.data.get("occupied", False)

        logger.info("Reflex: toilet stall %s → %s", stall_id, "occupied" if occupied else "vacant")

        await self._bus.publish(
            Event(
                type="toilet_status",
                data={"stall_id": stall_id, "occupied": occupied},
                source="reflex",
            )
        )

    # ------------------------------------------------------------------
    # MQTT subscription for toilet door sensors
    # ------------------------------------------------------------------

    async def start_toilet_mqtt(self, topic_prefix: str = "easeagent") -> None:
        """Subscribe to toilet sensor MQTT topics if mqtt_client is available."""
        if self._mqtt is None:
            return
        topic = f"{topic_prefix}/+/toilet/+/status"
        await self._mqtt.subscribe_topic(topic, self._on_toilet_mqtt_message)
        logger.info("ReflexEngine subscribed to MQTT: %s", topic)

    async def _on_toilet_mqtt_message(self, topic: str, payload: dict) -> None:
        parts = topic.split("/")
        stall_id = parts[3] if len(parts) >= 4 else "unknown"
        occupied = payload.get("occupied", False)

        await self._bus.publish(
            Event(
                type="toilet_sensor",
                data={"stall_id": stall_id, "occupied": occupied},
                source="mqtt",
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _publish_reflex_action(
        self,
        room_id: str,
        reason: str,
        actions: list[dict[str, Any]],
        safety: bool,
    ) -> None:
        await self._bus.publish(
            Event(
                type="reflex_action",
                data={
                    "room_id": room_id,
                    "reason": reason,
                    "actions": actions,
                    "safety": safety,
                    "timestamp": time.time(),
                },
                source="reflex",
                room_id=room_id,
            )
        )
