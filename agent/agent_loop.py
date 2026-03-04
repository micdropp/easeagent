"""EaseAgent core — Observe -> Think -> Act -> Reflect decision loop.

The Agent subscribes to EventBus events, builds a multimodal prompt,
sends it to the LLM, executes any returned tool calls, and records
the full decision trace to the database and Redis cache.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import numpy as np

from agent.llm_client import LLMClient, LLMResponse
from agent.prompt_builder import PromptBuilder
from agent.tool_executor import ToolExecutor
from agent.tools import TOOL_DEFINITIONS
from core.config import LLMSettings, get_settings
from core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)

TRIGGER_EVENTS = frozenset(
    {
        "face_arrived",
        "person_entered",
        "co2_high",
        "scene_patrol",
        "scene_change",
    }
)

REFLEX_ONLY_EVENTS = frozenset({"person_left", "face_left"})


class EaseAgent:
    """AI Agent that reacts to environment events with LLM-powered decisions.

    Lifecycle
    ---------
    1. Created in ``core.main.lifespan``
    2. Subscribes to EventBus events
    3. On each event: Observe -> Think -> Act -> Reflect
    4. Stopped on application shutdown
    """

    def __init__(
        self,
        event_bus: EventBus,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        tool_executor: ToolExecutor,
        redis_client: Any | None = None,
        db_session_factory: Any = None,
        perception_pipeline: Any | None = None,
        preference_learner: Any | None = None,
    ):
        self._event_bus = event_bus
        self._llm = llm_client
        self._prompt = prompt_builder
        self._executor = tool_executor
        self._redis = redis_client
        self._db_factory = db_session_factory
        self._perception = perception_pipeline
        self._learner = preference_learner

        self._settings = get_settings()
        self._cache_ttl = self._settings.redis.decision_cache_ttl

        self._pending: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def subscribe(self) -> None:
        """Register event handlers on the event bus."""
        for evt in TRIGGER_EVENTS:
            self._event_bus.subscribe(evt, self._on_event)
            logger.debug("Agent subscribed to '%s'", evt)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_event(self, event: Event) -> None:
        room_id = event.room_id or event.data.get("room_id", "unknown")
        dedup_key = f"{event.type}:{room_id}"

        if dedup_key in self._pending:
            logger.debug("Skipping duplicate in-flight event: %s", dedup_key)
            return

        asyncio.create_task(self._process_event(event, dedup_key))

    async def _process_event(self, event: Event, dedup_key: str) -> None:
        self._pending.add(dedup_key)
        try:
            await self._otar_cycle(event)
        except Exception:
            logger.exception("Agent OTAR cycle failed for event %s", event.type)
        finally:
            self._pending.discard(dedup_key)

    # ------------------------------------------------------------------
    # OTAR cycle
    # ------------------------------------------------------------------

    async def _otar_cycle(self, event: Event) -> None:
        t0 = time.perf_counter()
        room_id = event.room_id or event.data.get("room_id", "unknown")

        # --- OBSERVE ---
        frame = await self._grab_frame(event)

        cache_key = self._build_cache_key(event)
        cached = await self._check_cache(cache_key)
        if cached:
            logger.info(
                "Cache hit for %s — replaying cached decision", cache_key
            )
            await self._replay_cached(cached)
            latency_ms = (time.perf_counter() - t0) * 1000

            if self._db_factory:
                try:
                    from core.models import DecisionLog

                    log = DecisionLog(
                        room_id=room_id,
                        trigger_event=event.type,
                        agent_reasoning="[缓存命中] 重放上次决策",
                        tool_calls=json.dumps(
                            cached.get("tool_calls", []), ensure_ascii=False
                        ),
                        execution_results=json.dumps(
                            cached.get("results", []), ensure_ascii=False
                        ),
                        latency_ms=int(latency_ms),
                        success=True,
                    )
                    async with self._db_factory() as session:
                        session.add(log)
                        await session.commit()
                except Exception:
                    logger.exception("Failed to record cached decision log")

            await self._event_bus.publish(
                Event(
                    type="agent_decision",
                    data={
                        "room_id": room_id,
                        "trigger_event": event.type,
                        "reasoning": "[缓存命中] 重放上次决策",
                        "tool_calls": cached.get("tool_calls", []),
                        "results": cached.get("results", []),
                        "latency_ms": round(latency_ms, 1),
                        "provider": "cache",
                    },
                    source="agent",
                    room_id=room_id,
                )
            )
            return

        messages = await self._prompt.build(event, frame=frame)

        # --- THINK ---
        llm_response = await self._llm.chat(
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )

        # --- ACT ---
        results: list[dict[str, Any]] = []
        if llm_response.tool_calls:
            results = await self._executor.execute_many(llm_response.tool_calls)

        latency_ms = (time.perf_counter() - t0) * 1000

        # --- REFLECT ---
        await self._record_decision(event, llm_response, results, latency_ms)
        await self._cache_decision(cache_key, llm_response, results)
        await self._learn_from_decision(event, llm_response, results)

        await self._event_bus.publish(
            Event(
                type="agent_decision",
                data={
                    "room_id": room_id,
                    "trigger_event": event.type,
                    "reasoning": llm_response.content,
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in llm_response.tool_calls
                    ],
                    "results": results,
                    "latency_ms": round(latency_ms, 1),
                    "provider": llm_response.provider,
                },
                source="agent",
                room_id=room_id,
            )
        )

        logger.info(
            "Agent decision for [%s] room=%s: %d tool calls, %.0fms (%s)",
            event.type,
            room_id,
            len(llm_response.tool_calls),
            latency_ms,
            llm_response.provider,
        )

    # ------------------------------------------------------------------
    # Preference learning
    # ------------------------------------------------------------------

    async def _learn_from_decision(
        self,
        event: Event,
        response: LLMResponse,
        results: list[dict[str, Any]],
    ) -> None:
        if self._learner is None:
            return
        if not response.tool_calls:
            return
        try:
            room_id = event.room_id or event.data.get("room_id", "unknown")
            occupants: list[str] = []
            if self._perception and room_id:
                for o in self._perception.get_room_occupants(room_id):
                    eid = o.get("employee_id")
                    if eid:
                        occupants.append(eid)

            self._learner.learn_from_decision(
                {
                    "room_id": room_id,
                    "trigger_event": event.type,
                    "detected_people": occupants,
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                }
            )
        except Exception:
            logger.debug("Preference learning failed", exc_info=True)

    # ------------------------------------------------------------------
    # Frame grabbing
    # ------------------------------------------------------------------

    async def _grab_frame(self, event: Event) -> np.ndarray | None:
        camera_id = event.data.get("camera_id")
        if camera_id and self._perception:
            frame = await self._perception.get_annotated_frame(camera_id)
            if frame is not None:
                return frame

        if self._perception:
            cam_ids = self._perception.get_camera_ids()
            room_id = event.room_id or event.data.get("room_id")
            for cid in cam_ids:
                if self._perception._cam_room.get(cid) == room_id:
                    frame = await self._perception.get_annotated_frame(cid)
                    if frame is not None:
                        return frame
        return None

    # ------------------------------------------------------------------
    # Redis decision cache
    # ------------------------------------------------------------------

    def _build_cache_key(self, event: Event) -> str:
        room_id = event.room_id or event.data.get("room_id", "unknown")
        emp_id = event.data.get("employee_id", "any")
        return f"decision:{room_id}:{emp_id}"

    async def _check_cache(self, key: str) -> dict[str, Any] | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            logger.debug("Redis cache miss for %s", key, exc_info=True)
        return None

    async def _cache_decision(
        self,
        key: str,
        response: LLMResponse,
        results: list[dict[str, Any]],
    ) -> None:
        if not self._redis:
            return
        if not response.tool_calls:
            return
        try:
            payload = json.dumps(
                {
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    "results": results,
                },
                ensure_ascii=False,
            )
            await self._redis.set(key, payload, ex=self._cache_ttl)
        except Exception:
            logger.debug("Failed to cache decision for %s", key, exc_info=True)

    async def _replay_cached(self, cached: dict[str, Any]) -> None:
        """Replay tool calls from a cached decision."""
        from agent.llm_client import ToolCall

        tool_calls = cached.get("tool_calls", [])
        for tc_data in tool_calls:
            tc = ToolCall(
                id="cached",
                name=tc_data["name"],
                arguments=tc_data.get("arguments", {}),
            )
            await self._executor.execute(tc)

    # ------------------------------------------------------------------
    # Decision log persistence
    # ------------------------------------------------------------------

    async def _record_decision(
        self,
        event: Event,
        response: LLMResponse,
        results: list[dict[str, Any]],
        latency_ms: float,
    ) -> None:
        if not self._db_factory:
            return

        try:
            from core.models import DecisionLog

            room_id = event.room_id or event.data.get("room_id")
            occupants = []
            if self._perception and room_id:
                occupants = self._perception.get_room_occupants(room_id)

            tool_calls_json = json.dumps(
                [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
                ensure_ascii=False,
            )
            results_json = json.dumps(results, ensure_ascii=False)

            sensor_data = None
            try:
                from perception.sensor_collector import SensorCollector
                # sensor data is already part of the prompt; log a snapshot
                if hasattr(self, "_sensor") and self._sensor:
                    sd = self._sensor.get_latest(room_id)
                    if sd:
                        sensor_data = json.dumps(sd, ensure_ascii=False)
            except Exception:
                pass

            all_success = all(
                r.get("status") == "success" for r in results
            ) if results else True

            log = DecisionLog(
                room_id=room_id,
                trigger_event=event.type,
                detected_people=json.dumps(
                    [o.get("employee_id") for o in occupants],
                    ensure_ascii=False,
                ) if occupants else None,
                sensor_data=sensor_data,
                agent_reasoning=response.content[:2000] if response.content else None,
                tool_calls=tool_calls_json,
                execution_results=results_json,
                latency_ms=int(latency_ms),
                success=all_success,
            )

            async with self._db_factory() as session:
                session.add(log)
                await session.commit()

        except Exception:
            logger.exception("Failed to record decision log")
