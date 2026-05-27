from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date as date_type

from app.database import get_db
from app.api.deps import get_current_user

router = APIRouter(prefix="/conversations", tags=["conversations"])


def format_time_korean(dt) -> str:
    """datetime → 오전/오후 HH:MM 형식"""
    if dt is None:
        return ""
    hour = dt.hour
    minute = dt.minute
    if hour < 12:
        return f"오전 {hour:02d}:{minute:02d}"
    else:
        return f"오후 {(hour - 12):02d}:{minute:02d}"


@router.get("/{date}")
async def get_conversations_by_date(
    date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    날짜별 대화 원본 조회 (세션별 그룹화)
    JWT 토큰에서 patient_id 자동 추출
    보호자면 연결된 환자 데이터 조회
    """
    user_id = current_user["sub"]
    role = current_user["role"]

    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="날짜 형식이 올바르지 않습니다. (예: 2026-05-18)"
        )

    # patient_id 결정
    patient_id = await resolve_patient_id(user_id, role, db)

    # 해당 날짜의 세션 목록 조회
    sessions_result = await db.execute(text("""
        SELECT s.id, s.started_at, s.call_type
        FROM sessions s
        JOIN patients p ON p.id = s.patient_id
        WHERE p.id = CAST(:patient_id AS uuid)
          AND DATE(s.started_at) = :date
        ORDER BY s.started_at
    """), {"patient_id": patient_id, "date": report_date})

    sessions = sessions_result.fetchall()

    if not sessions:
        return {
            "chat_date": date,
            "sessions": []
        }

    session_list = []

    for session in sessions:
        session_id = str(session.id)

        # 해당 세션의 메시지 조회
        messages_result = await db.execute(text("""
            SELECT id, sender_type, content, created_at
            FROM messages
            WHERE session_id = CAST(:session_id AS uuid)
            ORDER BY created_at
        """), {"session_id": session_id})

        messages = messages_result.fetchall()

        message_list = [
            {
                "id": str(msg.id),
                "sender": "ai" if msg.sender_type == "ai" else "patient",
                "time": format_time_korean(msg.created_at),
                "text": msg.content,
            }
            for msg in messages
        ]

        session_list.append({
            "session_id": session_id,
            "session_time": format_time_korean(session.started_at),
            "call_type": session.call_type,
            "messages": message_list,
        })

    return {
        "chat_date": date,
        "sessions": session_list,
    }


async def resolve_patient_id(user_id: str, role: str, db: AsyncSession) -> str:
    """
    JWT user_id + role로 patient_id 결정
    - patient: 본인의 patient_id
    - guardian: 연결된 환자의 patient_id
    """
    if role == "patient":
        result = await db.execute(text("""
            SELECT p.id FROM patients p
            JOIN users u ON u.id = p.user_id
            WHERE u.id = CAST(:user_id AS uuid)
        """), {"user_id": user_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="환자 정보를 찾을 수 없습니다.")
        return str(row.id)

    elif role == "guardian":
        result = await db.execute(text("""
            SELECT p.id FROM patients p
            JOIN patient_guardians pg ON pg.patient_id = p.id
            JOIN guardians g ON g.id = pg.guardian_id
            JOIN users u ON u.id = g.user_id
            WHERE u.id = CAST(:user_id AS uuid)
            AND pg.status = 'accepted'
            LIMIT 1
        """), {"user_id": user_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="연결된 환자를 찾을 수 없습니다.")
        return str(row.id)

    raise HTTPException(status_code=403, detail="권한이 없습니다.")