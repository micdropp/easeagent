from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import get_session_factory
from core.event_bus import EventBus


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_mqtt_client(request: Request):
    return request.app.state.mqtt_client


def get_device_registry(request: Request):
    return request.app.state.device_registry


def get_redis(request: Request):
    return request.app.state.redis


def get_config() -> Settings:
    return get_settings()
