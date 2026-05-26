from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import uuid

from app.config import settings
from app.database import get_db
from app.models.session import Session
from app.models.user import User
from app.api.deps import get_current_user

class StartSessionRequest(BaseModel):
    patient_id: str
    call_type: str

router = APIRouter(tags=["calls"])

@router.post("/calls")
async def start_session(
    body: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    new_session = Session(
        id=str(uuid.uuid4()),
        patient_id=body.patient_id,
        call_type=body.call_type,
        started_at=datetime.utcnow(),  # 시간대 없이 timestamp로 처리
        ended_at=None,
        missed_count=0,
        emergency_sent=False,
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return {"session_id": f'{new_session.id}',
            "websocket_url": f'{settings.WS_BASE_URL}{settings.APP_PORT}/ws/calls?session_id={new_session.id}'
            }    # 프론트에서 이 id로 WS 연결


@router.post("/calls/{session_id}")
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