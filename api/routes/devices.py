from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import DeviceCreate, DeviceResponse, DeviceUpdate
from core.dependencies import get_db, get_device_registry
from core.models import Device

router = APIRouter()


@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    room_id: str | None = None,
    device_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Device)
    if room_id:
        stmt = stmt.where(Device.room_id == room_id)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, f"Device '{device_id}' not found")
    return device


@router.post("/", response_model=DeviceResponse, status_code=201)
async def create_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    registry=Depends(get_device_registry),
):
    existing = await db.execute(select(Device).where(Device.id == body.id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Device '{body.id}' already exists")

    device = Device(**body.model_dump())
    db.add(device)
    await db.flush()

    registry.register(device.id, device.device_type, device.room_id)
    return device


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, f"Device '{device_id}' not found")

    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(device, k, v)
    await db.flush()
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    registry=Depends(get_device_registry),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, f"Device '{device_id}' not found")
    await db.delete(device)
    registry.unregister(device_id)
