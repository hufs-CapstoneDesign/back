from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{patient_id}")
async def get_reports(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """날짜별 보고서 목록 조회"""
    result = await db.execute(text("""
        SELECT 
            id,
            report_date,
            mood,
            medication_summary,
            meal_summary,
            physical_summary,
            call_summary,
            session_count,
            last_updated
        FROM daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
        ORDER BY report_date DESC
        LIMIT 30
    """), {"patient_id": patient_id})

    rows = result.fetchall()

    if not rows:
        return {"reports": []}

    return {
        "reports": [
            {
                "id": str(row.id),
                "report_date": str(row.report_date),
                "mood": row.mood,
                "medication": row.medication_summary,
                "meal": row.meal_summary,
                "physical": row.physical_summary,
                "call_summary": row.call_summary,
                "session_count": row.session_count,
                "last_updated": str(row.last_updated),
            }
            for row in rows
        ]
    }


@router.get("/{patient_id}/{date}")
async def get_report_by_date(
    patient_id: str,
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """특정 날짜 보고서 조회"""
    result = await db.execute(text("""
        SELECT 
            id,
            report_date,
            mood,
            medication_summary,
            meal_summary,
            physical_summary,
            call_summary,
            session_count,
            last_updated
        FROM daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
          AND report_date = CAST(:date AS date)
    """), {"patient_id": patient_id, "date": date})

    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="해당 날짜의 보고서가 없습니다.")

    return {
        "id": str(row.id),
        "report_date": str(row.report_date),
        "mood": row.mood,
        "medication": row.medication_summary,
        "meal": row.meal_summary,
        "physical": row.physical_summary,
        "call_summary": row.call_summary,
        "session_count": row.session_count,
        "last_updated": str(row.last_updated),
    }


@router.get("/{patient_id}/{session_id}/messages")
async def get_session_messages(
    patient_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """특정 세션 대화 원본 조회"""
    result = await db.execute(text("""
        SELECT 
            id,
            sender_type,
            content,
            corrected_content,
            created_at
        FROM messages
        WHERE session_id = CAST(:session_id AS uuid)
          AND patient_id = CAST(:patient_id AS uuid)
        ORDER BY created_at
    """), {"session_id": session_id, "patient_id": patient_id})

    rows = result.fetchall()

    if not rows:
        return {"messages": []}

    return {
        "messages": [
            {
                "id": str(row.id),
                "sender_type": row.sender_type,
                "content": row.content,
                "corrected_content": row.corrected_content,
                "created_at": str(row.created_at),
            }
            for row in rows
        ]
    }