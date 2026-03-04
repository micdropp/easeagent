from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import close_db, init_db
from core.event_bus import EventBus
from monitor.health_check import HealthChecker

logger = logging.getLogger("easeagent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logging.basicConfig(
        level=logging.DEBUG if settings.server.debug else logging.INFO,
        format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    )
    for _noisy in ("openai", "httpx", "httpcore"):
        logging.getLogger(_noisy).setLevel(logging.INFO)
    logger.info("EaseAgent starting up...")

    Path("data").mkdir(exist_ok=True)

    await init_db()
    logger.info("Database initialized")

    event_bus = EventBus()
    await event_bus.start()
    app.state.event_bus = event_bus
    logger.info("EventBus started")

    try:
        redis_client = aioredis.Redis(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("Redis connected at %s:%s", settings.redis.host, settings.redis.port)
    except Exception:
        logger.warning("Redis not available, running without cache")
        app.state.redis = None

    try:
        chroma_client = chromadb.HttpClient(
            host=settings.chromadb.host,
            port=settings.chromadb.port,
        )
        chroma_client.heartbeat()
        app.state.chromadb = chroma_client
        logger.info("ChromaDB connected at %s:%s", settings.chromadb.host, settings.chromadb.port)
    except Exception:
        logger.warning("ChromaDB not available, running without vector store")
        app.state.chromadb = None

    from iot.mqtt_client import MQTTClient

    mqtt_client = MQTTClient(settings.mqtt)
    app.state.mqtt_client = mqtt_client
    await mqtt_client.start()

    from iot.device_registry import DeviceRegistry

    device_registry = DeviceRegistry(
        mqtt_client=mqtt_client,
        heartbeat_config=settings.device_heartbeat,
    )
    device_registry.set_event_bus(event_bus)
    app.state.device_registry = device_registry
    await device_registry.start()
    logger.info("DeviceRegistry started")

    from api.websocket.realtime import bind_event_bus
    bind_event_bus(event_bus)

    from perception.sensor_collector import SensorCollector

    sensor_collector = SensorCollector(
        mqtt_client=mqtt_client,
        event_bus=event_bus,
        topic_prefix=settings.mqtt.topic_prefix,
    )
    await sensor_collector.start()
    app.state.sensor_collector = sensor_collector
    logger.info("SensorCollector started")

    perception_pipeline = None
    if settings.ai.enabled:
        try:
            from perception.pipeline import PerceptionPipeline

            perception_pipeline = PerceptionPipeline(event_bus=event_bus)
            await perception_pipeline.start()
            app.state.perception = perception_pipeline
            logger.info("Perception pipeline started (ai.enabled=true)")
        except Exception:
            logger.exception("Failed to start perception pipeline, continuing without it")
            perception_pipeline = None
            app.state.perception = None
    else:
        app.state.perception = None
        logger.info("Perception pipeline disabled (ai.enabled=false)")

    # --- Phase 4: Memory layer ---
    memory_system = None
    try:
        from memory import MemorySystem
        from core.database import get_session_factory as _get_sf

        _db_factory_mem = _get_sf()
        memory_system = MemorySystem(
            db_session_factory=_db_factory_mem,
            chroma_client=app.state.chromadb,
        )
        app.state.memory = memory_system
        logger.info("MemorySystem initialised (explicit + implicit + context)")
    except Exception:
        logger.warning("MemorySystem init failed, running without memory layer", exc_info=True)
        app.state.memory = None

    # --- Phase 5: Reflex layer ---
    reflex_engine = None
    try:
        from reflex.engine import ReflexEngine

        reflex_engine = ReflexEngine(
            event_bus=event_bus,
            tool_executor=None,  # patched below after ToolExecutor is created
            mqtt_client=mqtt_client,
        )
        app.state.reflex = reflex_engine
        logger.info("ReflexEngine created (will subscribe after ToolExecutor)")
    except Exception:
        logger.warning("ReflexEngine init failed, running without reflex layer", exc_info=True)
        app.state.reflex = None

    # --- Phase 6: Feishu integration ---
    feishu_bot = None
    attendance_sync = None
    if settings.feishu.enabled:
        try:
            from feishu.bot import FeishuBot
            from feishu.attendance import AttendanceSync

            feishu_bot = FeishuBot(
                app_id=settings.feishu.app_id,
                app_secret=settings.feishu.app_secret,
                bot_webhook=settings.feishu.bot_webhook,
            )
            app.state.feishu_bot = feishu_bot

            attendance_sync = AttendanceSync(
                event_bus=event_bus,
                app_id=settings.feishu.app_id,
                app_secret=settings.feishu.app_secret,
                poll_interval=settings.feishu.attendance_poll_interval,
            )
            await attendance_sync.start()
            app.state.attendance_sync = attendance_sync

            if feishu_bot.available:
                logger.info("Feishu Bot initialised (webhook=%s)", bool(settings.feishu.bot_webhook))
            else:
                logger.info("Feishu Bot not configured (no credentials), notifications disabled")
        except Exception:
            logger.warning("Feishu init failed, running without Feishu", exc_info=True)
            app.state.feishu_bot = None
            app.state.attendance_sync = None
    else:
        app.state.feishu_bot = None
        app.state.attendance_sync = None
        logger.info("Feishu disabled (feishu.enabled=false)")

    # --- Phase 3: Cognition layer (Agent + ScenePatrol) ---
    ease_agent = None
    scene_patrol = None
    try:
        from agent.llm_client import LLMClient
        from agent.tool_executor import ToolExecutor
        from agent.prompt_builder import PromptBuilder
        from agent.conflict_resolver import ConflictResolver
        from agent.agent_loop import EaseAgent
        from agent.scene_patrol import ScenePatrol
        from core.database import get_session_factory

        db_factory = get_session_factory()

        llm_client = LLMClient(settings.llm)
        tool_executor = ToolExecutor(
            mqtt_client=mqtt_client,
            device_registry=device_registry,
            db_session_factory=db_factory,
            redis_client=app.state.redis,
            implicit_store=memory_system.implicit if memory_system else None,
            feishu_bot=feishu_bot,
        )
        conflict_resolver = ConflictResolver()
        prompt_builder = PromptBuilder(
            perception_pipeline=perception_pipeline,
            sensor_collector=sensor_collector,
            device_registry=device_registry,
            db_session_factory=db_factory,
            conflict_resolver=conflict_resolver,
            rag_retriever=memory_system.retriever if memory_system else None,
        )

        ease_agent = EaseAgent(
            event_bus=event_bus,
            llm_client=llm_client,
            prompt_builder=prompt_builder,
            tool_executor=tool_executor,
            redis_client=app.state.redis,
            db_session_factory=db_factory,
            perception_pipeline=perception_pipeline,
            preference_learner=memory_system.learner if memory_system else None,
        )
        ease_agent.subscribe()
        app.state.agent = ease_agent
        logger.info("EaseAgent cognitive layer initialised")

        if perception_pipeline is not None:
            scene_patrol = ScenePatrol(
                event_bus=event_bus,
                perception_pipeline=perception_pipeline,
                patrol_interval=settings.llm.patrol_interval,
                ssim_threshold=settings.llm.ssim_threshold,
            )
            await scene_patrol.start()
            perception_pipeline._scene_patrol = scene_patrol
            app.state.scene_patrol = scene_patrol
            logger.info("ScenePatrol started (interval=%.0fs)", settings.llm.patrol_interval)
        else:
            app.state.scene_patrol = None

    except Exception:
        logger.exception("Failed to initialise cognitive layer, running without Agent")
        app.state.agent = None
        app.state.scene_patrol = None

    # --- Wire up reflex engine with ToolExecutor ---
    if reflex_engine is not None:
        try:
            if ease_agent is not None:
                reflex_engine._executor = ease_agent._executor
                reflex_engine.subscribe()
                await reflex_engine.start_toilet_mqtt(settings.mqtt.topic_prefix)
                logger.info("ReflexEngine fully wired and subscribed")
            else:
                logger.warning(
                    "ReflexEngine skipped: no ToolExecutor available "
                    "(cognitive layer not initialised)"
                )
        except Exception:
            logger.warning("ReflexEngine wiring failed", exc_info=True)

    logger.info("EaseAgent ready — http://%s:%s", settings.server.host, settings.server.port)

    yield

    logger.info("EaseAgent shutting down...")
    if attendance_sync is not None:
        await attendance_sync.stop()
    if feishu_bot is not None:
        await feishu_bot.close()
    if reflex_engine is not None:
        await reflex_engine.stop()
    if scene_patrol is not None:
        await scene_patrol.stop()
    if perception_pipeline is not None:
        await perception_pipeline.stop()
    await sensor_collector.stop()
    await device_registry.stop()
    await mqtt_client.stop()
    if app.state.redis:
        await app.state.redis.aclose()
    if app.state.chromadb:
        app.state.chromadb = None
    await event_bus.stop()
    await close_db()
    logger.info("EaseAgent shutdown complete")


app = FastAPI(
    title="EaseAgent",
    description="AI Agent 智能办公室控制系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes import agent_log, devices, employees, preferences, rooms, toilet, video
from api.websocket import realtime
from feishu.mini_app_api import router as feishu_router

app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["preferences"])
app.include_router(agent_log.router, prefix="/api/agent-logs", tags=["agent-logs"])
app.include_router(toilet.router, prefix="/api/toilet", tags=["toilet"])
app.include_router(video.router, prefix="/api/video", tags=["video"])
app.include_router(realtime.router, prefix="/ws", tags=["websocket"])
app.include_router(feishu_router)


@app.get("/health")
async def health(request: Request, detail: bool = False):
    if detail:
        checker = HealthChecker(request.app.state)
        return await checker.check_all()
    return {"status": "ok", "service": "easeagent"}
