from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

EVENT_TO_CHANNEL = {
    "device_online": "device_status",
    "device_offline": "device_status",
    "toilet_status": "toilet_status",
    "sensor_data": "sensor_data",
    "agent_decision": "agent_log",
    "person_entered": "person_detection",
    "person_left": "person_detection",
    "face_arrived": "face_recognition",
    "face_left": "face_recognition",
    "sensor_update": "sensor_data",
    "co2_high": "sensor_data",
}


class ConnectionManager:
    """
    WebSocket 连接管理器。
    客户端连接时声明关注的频道，服务端按频道广播。
    频道: device_status / toilet_status / agent_log / sensor_data
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channels: list[str]):
        await ws.accept()
        for ch in channels:
            self._connections.setdefault(ch, []).append(ws)
        logger.info("WebSocket client connected, channels: %s", channels)

    def disconnect(self, ws: WebSocket):
        for ch, conns in self._connections.items():
            if ws in conns:
                conns.remove(ws)

    async def broadcast(self, channel: str, data: dict[str, Any]):
        message = json.dumps(
            {"channel": channel, "data": data}, ensure_ascii=False, default=str
        )
        disconnected = []
        for ws in self._connections.get(channel, []):
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        seen: set[int] = set()
        for conns in self._connections.values():
            for ws in conns:
                seen.add(id(ws))
        return len(seen)


manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    return manager


async def _forward_event_to_ws(event) -> None:
    channel = EVENT_TO_CHANNEL.get(event.type)
    if channel:
        await manager.broadcast(channel, {"event_type": event.type, **event.data})


def bind_event_bus(event_bus) -> None:
    for event_type in EVENT_TO_CHANNEL:
        event_bus.subscribe(event_type, _forward_event_to_ws)


@router.websocket("/realtime")
async def websocket_endpoint(ws: WebSocket):
    channels_param = ws.query_params.get("channels", "device_status,toilet_status")
    channels = [ch.strip() for ch in channels_param.split(",") if ch.strip()]

    await manager.connect(ws, channels)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "subscribe":
                    new_channels = msg.get("channels", [])
                    for ch in new_channels:
                        manager._connections.setdefault(ch, []).append(ws)
                elif action == "unsubscribe":
                    for ch in msg.get("channels", []):
                        conns = manager._connections.get(ch, [])
                        if ws in conns:
                            conns.remove(ws)
                elif action == "ping":
                    await ws.send_text(json.dumps({"action": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)
        logger.info("WebSocket client disconnected")
