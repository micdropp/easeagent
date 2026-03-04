from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import DecisionLogResponse
from core.dependencies import get_db
from core.models import DecisionLog

router = APIRouter()


@router.get("/", response_model=list[DecisionLogResponse])
async def list_logs(
    room_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    success: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DecisionLog).order_by(DecisionLog.created_at.desc())

    if room_id:
        stmt = stmt.where(DecisionLog.room_id == room_id)
    if date_from:
        stmt = stmt.where(DecisionLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(DecisionLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    if success is not None:
        stmt = stmt.where(DecisionLog.success == success)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats")
async def log_stats(
    room_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    base_stmt = select(DecisionLog)
    if room_id:
        base_stmt = base_stmt.where(DecisionLog.room_id == room_id)

    total = await db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )
    success_count = await db.execute(
        select(func.count()).select_from(
            base_stmt.where(DecisionLog.success == True).subquery()
        )
    )
    avg_latency = await db.execute(
        select(func.avg(DecisionLog.latency_ms)).select_from(
            base_stmt.subquery()
        )
    )

    total_val = total.scalar() or 0
    success_val = success_count.scalar() or 0

    return {
        "total_decisions": total_val,
        "successful": success_val,
        "failed": total_val - success_val,
        "success_rate": round(success_val / total_val, 3) if total_val > 0 else 0,
        "avg_latency_ms": round(avg_latency.scalar() or 0, 1),
    }


@router.get("/{log_id}", response_model=DecisionLogResponse)
async def get_log(log_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    result = await db.execute(
        select(DecisionLog).where(DecisionLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Decision log not found")
    return log
