"""Feishu attendance sync — pulls check-in/check-out records.

Runs as a periodic background task. When an employee checks in,
publishes an ``attendance_checkin`` event to the EventBus so that
the Agent can pre-load the environment (lights, AC).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, date
from typing import Any

import httpx

from core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)

ATTENDANCE_URL = "https://open.feishu.cn/open-apis/attendance/v1/user_daily_shifts/query"
CHECKIN_RECORD_URL = "https://open.feishu.cn/open-apis/attendance/v1/user_flows/query"


class AttendanceSync:
    """Periodically syncs Feishu attendance data and emits EventBus events."""

    def __init__(
        self,
        event_bus: EventBus,
        app_id: str = "",
        app_secret: str = "",
        poll_interval: float = 300.0,
    ):
        self._bus = event_bus
        self._app_id = app_id
        self._app_secret = app_secret
        self._poll_interval = poll_interval
        self._tenant_token: str = ""
        self._token_expires: float = 0.0
        self._task: asyncio.Task | None = None
        self._seen_checkins: set[str] = set()

    @property
    def available(self) -> bool:
        return bool(self._app_id and self._app_secret)

    async def start(self) -> None:
        if not self.available:
            logger.info("AttendanceSync disabled (no Feishu credentials)")
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("AttendanceSync started (poll every %.0fs)", self._poll_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("AttendanceSync stopped")

    async def _ensure_token(self) -> str:
        if self._tenant_token and time.time() < self._token_expires - 60:
            return self._tenant_token
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                )
                data = resp.json()
                self._tenant_token = data.get("tenant_access_token", "")
                self._token_expires = time.time() + data.get("expire", 7200)
        except Exception:
            logger.exception("Failed to get tenant_access_token for attendance")
        return self._tenant_token

    async def _loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("AttendanceSync poll error")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        token = await self._ensure_token()
        if not token:
            return

        today = date.today().isoformat()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                CHECKIN_RECORD_URL,
                headers=headers,
                json={
                    "user_ids": [],
                    "check_date_from": today,
                    "check_date_to": today,
                },
                params={"employee_type": "employee_id"},
            )
            data = resp.json()

        if data.get("code", -1) != 0:
            logger.warning("Attendance API error: %s", data.get("msg"))
            return

        records = data.get("data", {}).get("user_flow_results", [])
        for record in records:
            user_id = record.get("user_id", "")
            check_time = record.get("check_time", "")
            location_name = record.get("location_name", "")
            check_type = record.get("check_type", "")

            dedup_key = f"{user_id}:{check_time}"
            if dedup_key in self._seen_checkins:
                continue
            self._seen_checkins.add(dedup_key)

            if check_type in ("OnDuty", "on_duty", "1"):
                logger.info(
                    "Attendance checkin: user=%s time=%s location=%s",
                    user_id, check_time, location_name,
                )
                await self._bus.publish(
                    Event(
                        type="attendance_checkin",
                        data={
                            "employee_id": user_id,
                            "check_time": check_time,
                            "location": location_name,
                        },
                        source="feishu_attendance",
                    )
                )

        if len(self._seen_checkins) > 5000:
            self._seen_checkins.clear()
