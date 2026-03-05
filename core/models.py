from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    feishu_user_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    face_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    preferences: Mapped[list[Preference]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("employees.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(512))
    context: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped[Employee] = relationship(back_populates="preferences")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    floor: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    devices: Mapped[list[Device]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    device_type: Mapped[str] = mapped_column(String(32))
    room_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    protocol: Mapped[str] = mapped_column(String(32), default="mqtt")
    mqtt_topic: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    room: Mapped[Optional[Room]] = relationship(back_populates="devices")


class DecisionLog(Base):
    __tablename__ = "decision_logs"
    __table_args__ = (
        Index("ix_decision_logs_created_at", "created_at"),
        Index("ix_decision_logs_room_id", "room_id"),
        Index("ix_decision_logs_success", "success"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(128))
    detected_people: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sensor_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ToiletStall(Base):
    __tablename__ = "toilet_stalls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    floor: Mapped[str] = mapped_column(String(32))
    gender: Mapped[str] = mapped_column(String(16), default="unisex")
    is_occupied: Mapped[bool] = mapped_column(Boolean, default=False)
    sensor_device_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    last_status_change: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
