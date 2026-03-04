from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], Coroutine[Any, Any, None]]


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    room_id: str | None = None


class EventBus:
    """
    异步事件总线 — 系统内部发布-订阅通信核心。
    各模块通过 subscribe() 注册关注的事件类型，
    通过 publish() 广播事件给所有订阅者。
    """

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    def subscribe(self, event_type: str, handler: EventHandler):
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed %s to event '%s'", handler.__qualname__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event):
        await self._queue.put(event)

    def publish_nowait(self, event: Event):
        self._queue.put_nowait(event)

    async def _dispatch(self, event: Event):
        handlers = self._handlers.get(event.type, [])
        wildcard_handlers = self._handlers.get("*", [])
        all_handlers = handlers + wildcard_handlers

        if not all_handlers:
            logger.debug("No handlers for event type '%s'", event.type)
            return

        tasks = [
            asyncio.create_task(self._safe_call(h, event))
            for h in all_handlers
        ]
        await asyncio.gather(*tasks)

    async def _safe_call(self, handler: EventHandler, event: Event):
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Error in handler %s for event '%s'",
                handler.__qualname__,
                event.type,
            )

    async def _run_loop(self):
        self._running = True
        logger.info("EventBus started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in EventBus loop")

    async def start(self):
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("EventBus stopped")

    @property
    def is_running(self) -> bool:
        return self._running
