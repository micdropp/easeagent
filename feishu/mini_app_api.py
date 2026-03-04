"""Feishu mini-app backend API — routes consumed by the Feishu mini program.

Provides toilet status, preference management, and user profile endpoints
with Feishu user_access_token authentication.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])

USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


async def _get_feishu_user(authorization: str = Header("")) -> dict[str, Any]:
    """Validate Feishu user_access_token and return user info."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Feishu token")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                USER_INFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("code", -1) != 0:
                raise HTTPException(status_code=401, detail="Invalid Feishu token")
            return data.get("data", {})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Feishu auth failed")
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------------
# Toilet status (no auth required — public display)
# ------------------------------------------------------------------

@router.get("/toilet/status")
async def feishu_toilet_status(db: AsyncSession = Depends(get_db)):
    """Return toilet stall status for the mini-app."""
    from core.models import ToiletStall
    result = await db.execute(select(ToiletStall))
    stalls = result.scalars().all()
    return [
        {
            "stall_id": s.id,
            "floor": s.floor,
            "gender": s.gender,
            "is_occupied": s.is_occupied,
            "last_status_change": str(s.last_status_change) if s.last_status_change else None,
        }
        for s in stalls
    ]


# ------------------------------------------------------------------
# User profile
# ------------------------------------------------------------------

@router.get("/me")
async def feishu_me(user: dict = Depends(_get_feishu_user)):
    """Return the authenticated Feishu user's mapped EaseAgent profile."""
    return {
        "feishu_user_id": user.get("user_id"),
        "name": user.get("name"),
        "avatar": user.get("avatar_url"),
        "employee_id": user.get("employee_no", user.get("user_id")),
    }


# ------------------------------------------------------------------
# Preferences
# ------------------------------------------------------------------

@router.get("/preferences")
async def feishu_get_preferences(
    user: dict = Depends(_get_feishu_user),
    db: AsyncSession = Depends(get_db),
):
    """Get preferences for the authenticated Feishu user."""
    from core.models import Preference

    emp_id = user.get("employee_no", user.get("user_id", ""))
    stmt = select(Preference).where(Preference.employee_id == emp_id)
    result = await db.execute(stmt)
    prefs = result.scalars().all()

    return [
        {
            "id": p.id,
            "category": p.category,
            "key": p.key,
            "value": p.value,
            "context": p.context,
        }
        for p in prefs
    ]


@router.post("/preferences")
async def feishu_set_preference(
    body: dict[str, Any],
    user: dict = Depends(_get_feishu_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a preference for the authenticated Feishu user."""
    from core.models import Preference

    emp_id = user.get("employee_no", user.get("user_id", ""))
    stmt = select(Preference).where(
        Preference.employee_id == emp_id,
        Preference.category == body.get("category", ""),
        Preference.key == body.get("key", ""),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = body.get("value", "")
        existing.context = body.get("context")
    else:
        pref = Preference(
            employee_id=emp_id,
            category=body.get("category", ""),
            key=body.get("key", ""),
            value=body.get("value", ""),
            context=body.get("context"),
        )
        db.add(pref)
    await db.commit()

    return {"status": "ok", "employee_id": emp_id}
