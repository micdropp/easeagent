from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"


def _load_yaml(filename: str) -> dict[str, Any]:
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    for key, val in os.environ.items():
        raw = raw.replace(f"${{{key}}}", val)
        placeholder = f"${{{key}:-"
        while placeholder in raw:
            start = raw.index(placeholder)
            end_brace = raw.index("}", start + len(placeholder))
            default_val = raw[start + len(placeholder):end_brace]
            raw = raw[:start] + val + raw[end_brace + 1:]
    import re
    raw = re.sub(r"\$\{[^:]+:-([^}]*)\}", r"\1", raw)
    raw = re.sub(r"\$\{[^}]+\}", "", raw)
    return yaml.safe_load(raw) or {}


class MQTTSettings(BaseSettings):
    broker: str = "localhost"
    port: int = 1883
    client_id: str = "easeagent-core"
    topic_prefix: str = "easeagent"
    keepalive: int = 60
    reconnect_interval: int = 5


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    decision_cache_ttl: int = 7200


class DatabaseSettings(BaseSettings):
    url: str = "sqlite+aiosqlite:///./data/easeagent.db"
    echo: bool = False


class ChromaDBSettings(BaseSettings):
    host: str = "localhost"
    port: int = 8100
    persist_directory: str = "./data/chromadb"


class AISettings(BaseSettings):
    enabled: bool = False
    yolo_model: str = "yolov8n.pt"
    face_model: str = "buffalo_l"
    detection_interval: float = 1.0
    face_recognition_threshold: float = 0.6
    camera_width: int = 1280
    camera_height: int = 720


class LLMSettings(BaseSettings):
    provider: str = "dashscope"
    model: str = "qwen3.5-plus"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_retries: int = 2
    timeout: int = 30
    fallback_provider: str = "ollama"
    fallback_model: str = "qwen3.5:9b"
    fallback_base_url: str = "http://localhost:11434"
    patrol_interval: float = 30.0
    ssim_threshold: float = 0.85


class DeviceHeartbeatSettings(BaseSettings):
    interval: int = 30
    timeout: int = 90


class FeishuSettings(BaseSettings):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    bot_webhook: str = ""
    attendance_poll_interval: float = 300.0


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class Settings(BaseSettings):
    server: ServerSettings = Field(default_factory=ServerSettings)
    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    chromadb: ChromaDBSettings = Field(default_factory=ChromaDBSettings)
    ai: AISettings = Field(default_factory=AISettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    device_heartbeat: DeviceHeartbeatSettings = Field(
        default_factory=DeviceHeartbeatSettings
    )
    feishu: FeishuSettings = Field(default_factory=FeishuSettings)

    model_config = {"env_prefix": "EASEAGENT_", "env_nested_delimiter": "__"}


def _build_settings() -> Settings:
    yaml_data = _load_yaml("settings.yaml")

    sub_configs = {}
    field_map = {
        "server": ServerSettings,
        "mqtt": MQTTSettings,
        "redis": RedisSettings,
        "database": DatabaseSettings,
        "chromadb": ChromaDBSettings,
        "ai": AISettings,
        "llm": LLMSettings,
        "device_heartbeat": DeviceHeartbeatSettings,
        "feishu": FeishuSettings,
    }
    for key, cls in field_map.items():
        section = yaml_data.get(key, {})
        if isinstance(section, dict):
            cleaned = {k: v for k, v in section.items() if v is not None}
            sub_configs[key] = cls(**cleaned)

    return Settings(**sub_configs)


@lru_cache
def get_settings() -> Settings:
    return _build_settings()


def load_rooms_config() -> dict[str, Any]:
    return _load_yaml("rooms.yaml")


def load_agent_prompt() -> str:
    data = _load_yaml("agent_prompt.yaml")
    return data.get("system_prompt", "")
