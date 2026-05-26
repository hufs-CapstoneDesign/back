from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import uuid

from app.database import get_db
from app.api.deps import get_current_user

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleRequest(BaseModel):
    patient_id: str
    scheduled_time: str      # "HH:MM:SS" 형식
    days_of_week: list[int]  # [0, 1, 2, 3, 4, 5, 6]


class ScheduleUpdateRequest(BaseModel):
    scheduled_time: str
    days_of_week: list[int]


@router.get("/{patient_id}")
async def get_schedules(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(text("""
        SELECT id, scheduled_time, days_of_week, is_active
        FROM schedules
        WHERE patient_id = CAST(:patient_id AS uuid)
        ORDER BY scheduled_time
    """), {"patient_id": patient_id})

    rows = result.fetchall()
    return [
        {
            "schedule_id": str(row[0]),
            "scheduled_time": str(row[1]),
            "days_of_week": row[2],
            "is_active": row[3],
        }
        for row in rows
    ]


@router.post("")
async def create_schedule(
    request: ScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    schedule_id = str(uuid.uuid4())

    await db.execute(text("""
        INSERT INTO schedules (id, patient_id, scheduled_time, days_of_week, is_active, created_at, updated_at)
        VALUES (
            CAST(:id AS uuid),
            CAST(:patient_id AS uuid),
            :scheduled_time,
            :days_of_week,
            TRUE,
            NOW(),
            NOW()
        )
    """), {
        "id": schedule_id,
        "patient_id": request.patient_id,
        "scheduled_time": request.scheduled_time,
        "days_of_week": request.days_of_week,
    })

    await db.commit()
    return {"schedule_id": schedule_id, "status": "created"}


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(text("""
        UPDATE schedules
        SET scheduled_time = :scheduled_time,
            days_of_week = :days_of_week,
            updated_at = NOW()
        WHERE id = CAST(:schedule_id AS uuid)
        RETURNING id
    """), {
        "schedule_id": schedule_id,
        "scheduled_time": request.scheduled_time,
        "days_of_week": request.days_of_week,
    })

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")

    await db.commit()
    return {"schedule_id": schedule_id, "status": "updated"}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(text("""
        DELETE FROM schedules
        WHERE id = CAST(:schedule_id AS uuid)
        RETURNING id
    """), {"schedule_id": schedule_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")

    await db.commit()
    return {"schedule_id": schedule_id, "status": "deleted"}