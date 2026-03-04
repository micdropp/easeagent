from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from core.dependencies import get_db
from core.models import Employee

router = APIRouter()


@router.get("/", response_model=list[EmployeeResponse])
async def list_employees(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Employee)
    if is_active is not None:
        stmt = stmt.where(Employee.is_active == is_active)
    result = await db.execute(stmt.order_by(Employee.name))
    return result.scalars().all()


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(employee_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, f"Employee '{employee_id}' not found")
    return emp


@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(body: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Employee).where(Employee.id == body.id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Employee '{body.id}' already exists")
    emp = Employee(**body.model_dump())
    db.add(emp)
    await db.flush()
    return emp


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, f"Employee '{employee_id}' not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(emp, k, v)
    await db.flush()
    return emp


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(employee_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, f"Employee '{employee_id}' not found")
    await db.delete(emp)


@router.post("/{employee_id}/face", response_model=EmployeeResponse)
async def register_face(
    employee_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, f"Employee '{employee_id}' not found")

    image_bytes = await file.read()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Invalid image file")

    pipeline = getattr(request.app.state, "perception", None)
    if pipeline is not None:
        recognizer = pipeline.face_recognizer
    else:
        from perception.face_recognizer import FaceRecognizer

        recognizer = FaceRecognizer()

    ok = await recognizer.register_face(employee_id, frame)
    if not ok:
        raise HTTPException(422, "No face detected in the uploaded image")

    emp.face_registered = True
    await db.flush()
    return emp
