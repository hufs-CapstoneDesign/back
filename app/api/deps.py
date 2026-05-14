from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_access_token

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