from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import uuid

from app.database import get_db
from app.models.session import Session
from app.models.user import User

router = APIRouter(tags=["calls"])

@router.post("/calls")
async def start_session(
    patient_id: str,
    call_type: str,       # "scheduled" or "voluntary"
    db: AsyncSession = Depends(get_db),
):
    new_session = Session(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        call_type=call_type,
        started_at=datetime.utcnow(),  # 시간대 없이 timestamp로 처리
        ended_at=None,
        missed_count=0,
        emergency_sent=False,
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return {"session_id": f'{new_session.id}',
            "websocket_url": f'/ws/calls?session_id={new_session.id}'
            }    # 프론트에서 이 id로 WS 연결