from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import aiomqtt

from core.config import MQTTSettings

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class MQTTClient:
    """
    异步 MQTT 客户端封装。
    支持自动重连、topic 订阅回调注册、JSON 消息发布。
    """

    def __init__(self, config: MQTTSettings):
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def topic_prefix(self) -> str:
        return self._config.topic_prefix

    def on_message(self, topic_filter: str, handler: MessageHandler):
        self._handlers.setdefault(topic_filter, []).append(handler)

    async def subscribe_topic(self, topic_filter: str, handler: MessageHandler):
        """Register a handler and subscribe immediately if already connected."""
        self.on_message(topic_filter, handler)
        if self._client and self._connected:
            try:
                await self._client.subscribe(topic_filter)
                logger.debug("Late-subscribed to %s", topic_filter)
            except Exception:
                logger.warning("Failed to late-subscribe to %s", topic_filter)

    async def publish(self, topic: str, payload: dict | str, qos: int = 1):
        if not self._client or not self._connected:
            logger.warning("MQTT not connected, cannot publish to %s", topic)
            return
        msg = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        try:
            await self._client.publish(topic, msg, qos=qos)
            logger.debug("Published to %s: %s", topic, msg[:200])
        except Exception:
            logger.exception("Failed to publish to %s", topic)

    async def start(self):
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._connection_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False
        logger.info("MQTT client stopped")

    async def _connection_loop(self):
        self._running = True
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self._config.broker,
                    port=self._config.port,
                    identifier=self._config.client_id,
                    keepalive=self._config.keepalive,
                ) as client:
                    self._client = client
                    self._connected = True
                    logger.info(
                        "MQTT connected to %s:%s",
                        self._config.broker,
                        self._config.port,
                    )

                    for topic_filter in self._handlers:
                        await client.subscribe(topic_filter)
                        logger.debug("Subscribed to %s", topic_filter)

                    async for message in client.messages:
                        topic_str = str(message.topic)
                        try:
                            payload = json.loads(message.payload.decode())
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            payload = {"raw": message.payload.decode(errors="replace")}

                        await self._dispatch(topic_str, payload)

            except aiomqtt.MqttError as e:
                self._connected = False
                if self._running:
                    logger.warning(
                        "MQTT connection lost: %s. Reconnecting in %ds...",
                        e,
                        self._config.reconnect_interval,
                    )
                    await asyncio.sleep(self._config.reconnect_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self._connected = False
                if self._running:
                    logger.exception("Unexpected MQTT error, reconnecting...")
                    await asyncio.sleep(self._config.reconnect_interval)

    async def _dispatch(self, topic: str, payload: dict[str, Any]):
        for topic_filter, handlers in self._handlers.items():
            if self._topic_matches(topic_filter, topic):
                for handler in handlers:
                    try:
                        await handler(topic, payload)
                    except Exception:
                        logger.exception(
                            "Error in MQTT handler for topic %s", topic
                        )

    @staticmethod
    def _topic_matches(filter_pattern: str, topic: str) -> bool:
        filter_parts = filter_pattern.split("/")
        topic_parts = topic.split("/")

        for i, fp in enumerate(filter_parts):
            if fp == "#":
                return True
            if i >= len(topic_parts):
                return False
            if fp != "+" and fp != topic_parts[i]:
                return False

        return len(filter_parts) == len(topic_parts)
