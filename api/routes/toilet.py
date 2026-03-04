from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import ToiletStallCreate, ToiletStallResponse, ToiletStallUpdate
from core.dependencies import get_db, get_event_bus
from core.event_bus import Event, EventBus
from core.models import ToiletStall

router = APIRouter()


@router.get("/status", response_model=list[ToiletStallResponse])
async def get_all_toilet_status(
    floor: str | None = None,
    gender: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ToiletStall)
    if floor:
        stmt = stmt.where(ToiletStall.floor == floor)
    if gender:
        stmt = stmt.where(ToiletStall.gender == gender)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/status/{stall_id}", response_model=ToiletStallResponse)
async def get_stall_status(stall_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ToiletStall).where(ToiletStall.id == stall_id)
    )
    stall = result.scalar_one_or_none()
    if not stall:
        raise HTTPException(404, f"Stall '{stall_id}' not found")
    return stall


@router.post("/stalls", response_model=ToiletStallResponse, status_code=201)
async def create_stall(body: ToiletStallCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(ToiletStall).where(ToiletStall.id == body.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Stall '{body.id}' already exists")
    stall = ToiletStall(**body.model_dump())
    db.add(stall)
    await db.flush()
    return stall


@router.put("/status/{stall_id}", response_model=ToiletStallResponse)
async def update_stall_status(
    stall_id: str,
    body: ToiletStallUpdate,
    db: AsyncSession = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
):
    result = await db.execute(
        select(ToiletStall).where(ToiletStall.id == stall_id)
    )
    stall = result.scalar_one_or_none()
    if not stall:
        raise HTTPException(404, f"Stall '{stall_id}' not found")

    changed = stall.is_occupied != body.is_occupied
    stall.is_occupied = body.is_occupied
    stall.last_status_change = datetime.now()
    await db.flush()

    if changed:
        await event_bus.publish(
            Event(
                type="toilet_status",
                data={
                    "stall_id": stall.id,
                    "floor": stall.floor,
                    "gender": stall.gender,
                    "is_occupied": stall.is_occupied,
                },
                source="toilet_api",
            )
        )

    return stall


@router.get("/summary")
async def toilet_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ToiletStall))
    stalls = result.scalars().all()

    floors: dict[str, dict] = {}
    for stall in stalls:
        if stall.floor not in floors:
            floors[stall.floor] = {"total": 0, "occupied": 0, "free": 0}
        floors[stall.floor]["total"] += 1
        if stall.is_occupied:
            floors[stall.floor]["occupied"] += 1
        else:
            floors[stall.floor]["free"] += 1

    return {"floors": floors}
