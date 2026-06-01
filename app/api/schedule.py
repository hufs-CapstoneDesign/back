from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid

from app.database import get_db
from app.api.deps import get_current_user
from app.schemas.schedule import ScheduleUpdateRequest

router = APIRouter(prefix="/schedules", tags=["schedules"])



@router.get("/{patient_id}")
async def get_schedules(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # ai_call_enabled 조회
    patient_result = await db.execute(text("""
        SELECT ai_call_enabled FROM patients
        WHERE id = CAST(:patient_id AS uuid)
    """), {"patient_id": patient_id})
    patient_row = patient_result.fetchone()

    if not patient_row:
        raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다.")

    # 스케줄 목록 조회
    result = await db.execute(text("""
        SELECT days_of_week, scheduled_time
        FROM schedules
        WHERE patient_id = CAST(:patient_id AS uuid)
        AND is_active = TRUE
        ORDER BY scheduled_time
    """), {"patient_id": patient_id})

    rows = result.fetchall()

    schedule_list = []
    for row in rows:
        for day in row[0]:
            schedule_list.append({
                "day_of_week": day,
                "call_time": str(row[1])[:5],  # "HH:MM"
            })

    return {
        "ai_call_enabled": patient_row[0],
        "schedule_list": schedule_list,
    }


@router.put("/{patient_id}")
async def update_schedules(
    patient_id: str,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # ai_call_enabled 업데이트
    await db.execute(text("""
        UPDATE patients
        SET ai_call_enabled = :ai_call_enabled, updated_at = NOW()
        WHERE id = CAST(:patient_id AS uuid)
    """), {
        "ai_call_enabled": request.ai_call_enabled,
        "patient_id": patient_id,
    })

    await db.execute(text("""
        DELETE FROM scheduled_calls
        WHERE schedule_id IN (
            SELECT id FROM schedules
            WHERE patient_id = CAST(:patient_id AS uuid)
        )
    """), {"patient_id": patient_id})

    # 기존 스케줄 전부 삭제
    await db.execute(text("""
        DELETE FROM schedules
        WHERE patient_id = CAST(:patient_id AS uuid)
    """), {"patient_id": patient_id})

    # 새 스케줄 삽입
    # call_time이 같으면 days_of_week 배열로 묶기
    time_to_days: dict[str, list[int]] = {}
    for item in request.schedule_list:
        if item.call_time not in time_to_days:
            time_to_days[item.call_time] = []
        time_to_days[item.call_time].append(item.day_of_week)

    for call_time, days in time_to_days.items():
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
            "id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "scheduled_time": f"{call_time}:00",
            "days_of_week": days,
        })

    await db.commit()
    return {"status": "updated"}