from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.schemas import RoomCreate, RoomResponse, RoomUpdate
from core.dependencies import get_db
from core.models import Room

router = APIRouter()


@router.get("/", response_model=list[RoomResponse])
async def list_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).order_by(Room.name))
    return result.scalars().all()


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Room).where(Room.id == room_id).options(selectinload(Room.devices))
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, f"Room '{room_id}' not found")
    return room


@router.post("/", response_model=RoomResponse, status_code=201)
async def create_room(body: RoomCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Room).where(Room.id == body.id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Room '{body.id}' already exists")
    room = Room(**body.model_dump())
    db.add(room)
    await db.flush()
    return room


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    body: RoomUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, f"Room '{room_id}' not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(room, k, v)
    await db.flush()
    return room


@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, f"Room '{room_id}' not found")
    await db.delete(room)
