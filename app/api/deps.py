from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """JWT 토큰 검증 — 모든 인증 필요 API에서 사용"""
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )
    return payload


def require_guardian(current_user: dict = Depends(get_current_user)) -> dict:
    """보호자만 접근 가능"""
    if current_user["role"] != "guardian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="보호자만 접근할 수 있습니다.",
        )
    return current_user


def require_patient(current_user: dict = Depends(get_current_user)) -> dict:
    """환자만 접근 가능"""
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="환자만 접근할 수 있습니다.",
        )
    return current_user


async def get_patient_id(current_user: dict, db: AsyncSession) -> str:
    user_id = current_user["sub"]
    role = current_user["role"]

    if role == "patient":
        result = await db.execute(text("""
            SELECT id FROM patients WHERE user_id = CAST(:user_id AS uuid)
        """), {"user_id": user_id})

    elif role == "guardian":
        result = await db.execute(text("""
            SELECT p.id FROM patients p
            JOIN patient_guardians pg ON p.id = pg.patient_id
            JOIN guardians g ON pg.guardian_id = g.id
            WHERE g.user_id = CAST(:user_id AS uuid)
            AND pg.status = 'accepted'
        """), {"user_id": user_id})

    else:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="연결된 환자를 찾을 수 없습니다.")

    return str(row[0])