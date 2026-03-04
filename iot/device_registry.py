from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from core.config import DeviceHeartbeatSettings
from core.event_bus import Event

logger = logging.getLogger(__name__)


@dataclass
class DeviceState:
    device_id: str
    device_type: str
    room_id: str | None = None
    is_online: bool = False
    last_heartbeat: datetime | None = None
    state: dict[str, Any] = field(default_factory=dict)


class DeviceRegistry:
    """
    设备注册中心 — 跟踪所有 IoT 设备的在线状态和当前状态。
    通过 MQTT 心跳检测设备在线/离线。
    """

    def __init__(self, mqtt_client, heartbeat_config: DeviceHeartbeatSettings):
        self._mqtt = mqtt_client
        self._config = heartbeat_config
        self._devices: dict[str, DeviceState] = {}
        self._check_task: asyncio.Task | None = None
        self._running = False
        self._event_bus = None

    def set_event_bus(self, event_bus):
        self._event_bus = event_bus

    def register(
        self,
        device_id: str,
        device_type: str,
        room_id: str | None = None,
    ):
        if device_id not in self._devices:
            self._devices[device_id] = DeviceState(
                device_id=device_id,
                device_type=device_type,
                room_id=room_id,
            )
            logger.info("Registered device: %s (%s) in room %s", device_id, device_type, room_id)

    def unregister(self, device_id: str):
        self._devices.pop(device_id, None)

    def get(
        self,
        room_id: str,
        device_type: str,
        device_id: str | None = None,
    ) -> DeviceState | None:
        if device_id:
            return self._devices.get(device_id)
        for dev in self._devices.values():
            if dev.room_id == room_id and dev.device_type == device_type:
                return dev
        return None

    def get_by_id(self, device_id: str) -> DeviceState | None:
        return self._devices.get(device_id)

    def get_room_devices(
        self, room_id: str, device_type: str | None = None
    ) -> list[DeviceState]:
        result = [d for d in self._devices.values() if d.room_id == room_id]
        if device_type:
            result = [d for d in result if d.device_type == device_type]
        return result

    def get_all_devices(self) -> list[DeviceState]:
        return list(self._devices.values())

    def get_online_devices(self) -> list[DeviceState]:
        return [d for d in self._devices.values() if d.is_online]

    async def update_state(self, device_id: str, state_update: dict[str, Any]):
        dev = self._devices.get(device_id)
        if dev:
            dev.state.update(state_update)

    async def _handle_heartbeat(self, topic: str, payload: dict[str, Any]):
        parts = topic.split("/")
        if len(parts) < 4:
            return
        device_id = payload.get("device_id") or parts[-2]
        device_type = payload.get("device_type", "unknown")
        room_id = payload.get("room_id")

        if device_id not in self._devices:
            self.register(device_id, device_type, room_id)

        dev = self._devices[device_id]
        was_offline = not dev.is_online
        dev.is_online = True
        dev.last_heartbeat = datetime.now()

        if was_offline:
            logger.info("Device %s came online", device_id)
            if self._event_bus:
                await self._event_bus.publish(
                    Event(
                        type="device_online",
                        data={"device_id": device_id, "device_type": device_type},
                        source="device_registry",
                        room_id=room_id,
                    )
                )

    async def _check_heartbeats(self):
        while self._running:
            try:
                await asyncio.sleep(self._config.interval)
                timeout = timedelta(seconds=self._config.timeout)
                now = datetime.now()

                for dev in self._devices.values():
                    if not dev.is_online:
                        continue
                    if dev.last_heartbeat and (now - dev.last_heartbeat) > timeout:
                        dev.is_online = False
                        logger.warning("Device %s went offline (heartbeat timeout)", dev.device_id)
                        if self._event_bus:
                            await self._event_bus.publish(
                                Event(
                                    type="device_offline",
                                    data={
                                        "device_id": dev.device_id,
                                        "device_type": dev.device_type,
                                    },
                                    source="device_registry",
                                    room_id=dev.room_id,
                                )
                            )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error checking device heartbeats")

    async def start(self):
        topic_prefix = self._mqtt.topic_prefix
        self._mqtt.on_message(
            f"{topic_prefix}/+/+/heartbeat", self._handle_heartbeat
        )
        self._running = True
        self._check_task = asyncio.create_task(self._check_heartbeats())
        logger.info("DeviceRegistry heartbeat monitor started")

    async def stop(self):
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("DeviceRegistry stopped")
