from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    各组件健康检查。
    由 /health 端点和 watchdog 调用。
    """

    def __init__(self, app_state):
        self._state = app_state

    async def check_all(self) -> dict[str, Any]:
        results = {
            "timestamp": datetime.now().isoformat(),
            "mqtt": await self._check_mqtt(),
            "redis": await self._check_redis(),
            "database": await self._check_database(),
            "event_bus": self._check_event_bus(),
            "devices": self._check_devices(),
        }
        results["healthy"] = all(
            v.get("status") == "ok" if isinstance(v, dict) else True
            for v in results.values()
            if isinstance(v, dict)
        )
        return results

    async def _check_mqtt(self) -> dict[str, Any]:
        mqtt = getattr(self._state, "mqtt_client", None)
        if mqtt is None:
            return {"status": "not_configured"}
        return {
            "status": "ok" if mqtt.is_connected else "disconnected",
            "connected": mqtt.is_connected,
        }

    async def _check_redis(self) -> dict[str, Any]:
        redis_client = getattr(self._state, "redis", None)
        if redis_client is None:
            return {"status": "not_configured"}
        try:
            await redis_client.ping()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _check_database(self) -> dict[str, Any]:
        try:
            from core.database import get_session_factory
            factory = get_session_factory()
            async with factory() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _check_event_bus(self) -> dict[str, Any]:
        bus = getattr(self._state, "event_bus", None)
        if bus is None:
            return {"status": "not_configured"}
        return {"status": "ok" if bus.is_running else "stopped", "running": bus.is_running}

    def _check_devices(self) -> dict[str, Any]:
        registry = getattr(self._state, "device_registry", None)
        if registry is None:
            return {"status": "not_configured"}
        all_devices = registry.get_all_devices()
        online = registry.get_online_devices()
        return {
            "status": "ok",
            "total": len(all_devices),
            "online": len(online),
        }
