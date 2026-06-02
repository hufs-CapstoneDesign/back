from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import uuid

from app.config import settings
from app.database import get_db
from app.schemas.session import StartSessionRequest, StartSessionResponse, EndSessionResponse, RequestCallResponse
from app.models.session import Session
from app.models.user import User
from app.api.deps import get_current_user, get_patient_id
from app.fcm.fcm import send_call_notification


router = APIRouter(tags=["calls"])

@router.post("/calls", response_model=StartSessionResponse)
async def start_session(
    body: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient_id = await get_patient_id(current_user, db)

    new_session = Session(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        call_type=body.call_type,
        started_at=datetime.utcnow(),
        ended_at=None,
        missed_count=0,
        emergency_sent=False,
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return {
        "session_id": str(new_session.id),
        "websocket_url": f'{settings.WS_BASE_URL}{settings.APP_PORT}/ws/calls?session_id={new_session.id}'
    }


@router.patch("/calls/{session_id}", response_model=EndSessionResponse)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(text("""
        UPDATE sessions 
        SET ended_at = :ended_at
        WHERE id = CAST(:session_id AS uuid)
        RETURNING id
    """), {
        "session_id": session_id,
        "ended_at": datetime.utcnow(),
    })

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    await db.commit()
    return {"session_id": session_id, "status": "ended"}


@router.post("/calls/request", response_model=RequestCallResponse)
async def request_call(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 접근할 수 있습니다.")

    patient_id = await get_patient_id(current_user, db)

    result = await db.execute(text("""
        SELECT fcm_token FROM patients
        WHERE id = CAST(:patient_id AS uuid)
        AND fcm_token IS NOT NULL
    """), {"patient_id": patient_id})

    row = result.fetchone()
    if not row:
        return {
            "success": False,
            "message": "등록된 디바이스 토큰(FCM)이 없습니다."
        }

    try:
        send_call_notification(row[0], call_type="requested")
        return {
            "success": True,
            "message": "환자에게 AI 통화 요청 푸시를 성공적으로 발송했습니다.",
        }
    except Exception as e:
        print(f"FCM 발신 실패: {e}")
        return {
            "success": False,
            "message": "푸시 발송에 실패했습니다."
        }