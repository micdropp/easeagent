from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.event_bus import Event, EventBus
from iot.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

CO2_HIGH_THRESHOLD = 1000  # ppm
SENSOR_UPDATE_INTERVAL = 30.0  # seconds


class SensorCollector:
    """Subscribes to sensor MQTT topics and publishes events to the EventBus.

    Topic pattern: ``easeagent/+/sensor/+/data``
    (e.g. ``easeagent/zone_a/sensor/env_01/data``)

    Cached values can be retrieved via ``get_latest(room_id)`` for prompt
    building in later phases.
    """

    def __init__(
        self,
        mqtt_client: MQTTClient,
        event_bus: EventBus,
        topic_prefix: str = "easeagent",
        co2_threshold: float = CO2_HIGH_THRESHOLD,
        update_interval: float = SENSOR_UPDATE_INTERVAL,
    ):
        self._mqtt = mqtt_client
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._co2_threshold = co2_threshold
        self._update_interval = update_interval

        self._cache: dict[str, dict[str, Any]] = {}
        self._last_publish: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        topic_filter = f"{self._topic_prefix}/+/sensor/+/data"
        self._mqtt.on_message(topic_filter, self._handle_sensor_msg)
        logger.info("SensorCollector subscribed to %s", topic_filter)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("SensorCollector stopped")

    def get_latest(self, room_id: str) -> dict[str, Any] | None:
        return self._cache.get(room_id)

    def get_all_latest(self) -> dict[str, dict[str, Any]]:
        return dict(self._cache)

    async def _handle_sensor_msg(self, topic: str, payload: dict[str, Any]) -> None:
        parts = topic.split("/")
        if len(parts) < 5:
            return
        room_id = parts[1]

        temperature = payload.get("temperature")
        humidity = payload.get("humidity")
        co2 = payload.get("co2")

        entry = self._cache.get(room_id, {})
        entry["room_id"] = room_id
        if temperature is not None:
            entry["temperature"] = temperature
        if humidity is not None:
            entry["humidity"] = humidity
        if co2 is not None:
            entry["co2"] = co2
        entry["_ts"] = time.time()
        self._cache[room_id] = entry

        if co2 is not None and co2 > self._co2_threshold:
            await self._event_bus.publish(
                Event(
                    type="co2_high",
                    data={"room_id": room_id, "co2_value": co2},
                    source="sensor_collector",
                )
            )

        now = time.monotonic()
        last = self._last_publish.get(room_id, 0.0)
        if now - last >= self._update_interval:
            self._last_publish[room_id] = now
            await self._event_bus.publish(
                Event(
                    type="sensor_update",
                    data={
                        "room_id": room_id,
                        "temperature": entry.get("temperature"),
                        "humidity": entry.get("humidity"),
                        "co2": entry.get("co2"),
                    },
                    source="sensor_collector",
                )
            )
