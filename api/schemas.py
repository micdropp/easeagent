from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Device ──

class DeviceCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    device_type: str = Field(..., pattern=r"^(light|ac|screen|fresh_air|sensor|toilet_sensor|curtain)$")
    room_id: Optional[str] = None
    protocol: str = "mqtt"
    mqtt_topic: Optional[str] = None
    config_json: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    room_id: Optional[str] = None
    protocol: Optional[str] = None
    mqtt_topic: Optional[str] = None
    config_json: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    device_type: str
    room_id: Optional[str]
    protocol: str
    mqtt_topic: Optional[str]
    is_online: bool
    last_heartbeat: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Room ──

class RoomCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    floor: Optional[str] = None
    capacity: Optional[int] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    floor: Optional[str] = None
    capacity: Optional[int] = None
    is_active: Optional[bool] = None


class RoomResponse(BaseModel):
    id: str
    name: str
    floor: Optional[str]
    capacity: Optional[int]
    is_active: bool

    model_config = {"from_attributes": True}


# ── Employee ──

class EmployeeCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    email: Optional[str] = None
    feishu_user_id: Optional[str] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    feishu_user_id: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    id: str
    name: str
    email: Optional[str]
    feishu_user_id: Optional[str]
    face_registered: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Preference ──

class PreferenceSet(BaseModel):
    employee_id: str
    category: str = Field(..., description="light / ac / fresh_air / screen")
    key: str = Field(..., description="brightness / color_temp / temperature / mode / level")
    value: str
    context: Optional[str] = Field(None, description="情境标签: 独自办公 / 开会 / 午休")


class PreferenceResponse(BaseModel):
    id: int
    employee_id: str
    category: str
    key: str
    value: str
    context: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Decision Log ──

class DecisionLogResponse(BaseModel):
    id: int
    room_id: Optional[str]
    trigger_event: str
    detected_people: Optional[str]
    sensor_data: Optional[str]
    agent_reasoning: Optional[str]
    tool_calls: Optional[str]
    execution_results: Optional[str]
    latency_ms: Optional[int]
    success: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Toilet ──

class ToiletStallResponse(BaseModel):
    id: str
    floor: str
    gender: str
    is_occupied: bool
    last_status_change: Optional[datetime]

    model_config = {"from_attributes": True}


class ToiletStallCreate(BaseModel):
    id: str
    floor: str
    gender: str = "unisex"
    sensor_device_id: Optional[str] = None


class ToiletStallUpdate(BaseModel):
    is_occupied: bool
