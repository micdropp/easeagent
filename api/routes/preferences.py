from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import PreferenceResponse, PreferenceSet
from core.dependencies import get_db
from core.models import Employee, Preference

router = APIRouter()


@router.get("/{employee_id}", response_model=list[PreferenceResponse])
async def get_preferences(
    employee_id: str,
    category: str | None = None,
    context: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Preference).where(Preference.employee_id == employee_id)
    if category:
        stmt = stmt.where(Preference.category == category)
    if context:
        stmt = stmt.where(Preference.context == context)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=PreferenceResponse, status_code=201)
async def set_preference(body: PreferenceSet, db: AsyncSession = Depends(get_db)):
    emp_result = await db.execute(
        select(Employee).where(Employee.id == body.employee_id)
    )
    if not emp_result.scalar_one_or_none():
        raise HTTPException(404, f"Employee '{body.employee_id}' not found")

    conditions = [
        Preference.employee_id == body.employee_id,
        Preference.category == body.category,
        Preference.key == body.key,
    ]
    if body.context:
        conditions.append(Preference.context == body.context)
    else:
        conditions.append(Preference.context.is_(None))

    result = await db.execute(select(Preference).where(and_(*conditions)))
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = body.value
        await db.flush()
        return existing

    pref = Preference(**body.model_dump())
    db.add(pref)
    await db.flush()
    return pref


@router.delete("/{preference_id}", status_code=204)
async def delete_preference(
    preference_id: int, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Preference).where(Preference.id == preference_id)
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(404, "Preference not found")
    await db.delete(pref)
