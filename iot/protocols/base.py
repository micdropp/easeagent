from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DeviceProtocol(ABC):
    """
    设备协议适配器基类。
    每种设备协议(MQTT直连/Zigbee网关/红外转发器等)继承此类，
    对上层暴露统一的 send_command / get_status 接口。
    """

    @abstractmethod
    async def send_command(self, device_id: str, command: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_status(self, device_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def disconnect(self):
        ...


class MQTTDirectProtocol(DeviceProtocol):
    """MQTT 直连协议 — 大多数智能设备的默认通信方式。"""

    def __init__(self, mqtt_client, topic_prefix: str):
        self._mqtt = mqtt_client
        self._topic_prefix = topic_prefix

    async def send_command(self, device_id: str, command: dict[str, Any]) -> dict[str, Any]:
        topic = f"{self._topic_prefix}/{device_id}/cmd"
        await self._mqtt.publish(topic, command)
        return {"status": "sent", "device_id": device_id, "topic": topic}

    async def get_status(self, device_id: str) -> dict[str, Any]:
        return {"device_id": device_id, "status": "unknown"}

    async def connect(self):
        pass

    async def disconnect(self):
        pass
