import uuid
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.auth import (
    SignupRequest, LoginRequest,
    ConnectPatientRequest, TokenResponse, UserResponse
)
from app.api.deps import get_current_user
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    """회원가입 - username으로 회원가입"""
    async with AsyncSessionLocal() as db:
        try:
            # username 중복 확인
            result = await db.execute(text("""
                SELECT id FROM users WHERE username = :username
            """), {"username": request.username})

            if result.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="이미 등록된 아이디입니다.",
                )

            # 유저 생성
            user_id = str(uuid.uuid4())
            hashed_pw = hash_password(request.password)

            await db.execute(text("""
                INSERT INTO users (id, username, name, phone, password, role, profile, created_at)
                VALUES (CAST(:id AS uuid), :username, :name, :phone, :password, :role, '{}', NOW())
            """), {
                "id": user_id,
                "username": request.username,
                "name": request.name,
                "phone": request.phone,
                "password": hashed_pw,
                "role": request.role,
            })
            await db.commit()

            token = create_access_token(user_id=user_id, role=request.role)
            return TokenResponse(
                access_token=token,
                token_type="bearer",
                user_id=user_id,
                role=request.role,
                name=request.name,
            )
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            print(f"회원가입 에러: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"회원가입 중 오류가 발생했습니다: {str(e)}",
            )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """로그인 - username/password"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, name, password, role FROM users WHERE username = :username
        """), {"username": request.username})
        user = result.fetchone()

    if not user or not verify_password(request.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(user_id=str(user.id), role=user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=str(user.id),
        role=user.role,
        name=user.name,
    )


@router.post("/connect-patient", response_model=UserResponse)
async def connect_patient(
    request: ConnectPatientRequest,
    current_user: dict = Depends(get_current_user)
):
    """보호자가 환자 username으로 연결"""
    # 보호자만 호출 가능
    if current_user["role"] != "guardian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="보호자만 접근할 수 있습니다.",
        )
    
    async with AsyncSessionLocal() as db:
        # 환자 조회
        result = await db.execute(text("""
            SELECT id, name, role FROM users
            WHERE username = :username AND role = 'patient'
        """), {"username": request.patient_username})
        patient = result.fetchone()

        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 아이디의 환자를 찾을 수 없습니다.",
            )
        
        # 보호자-환자 연결 (patients의 guardian_id 업데이트)
        await db.execute(text("""
            UPDATE users SET guardian_id = CAST(:guardian_id AS uuid)
            WHERE id = CAST(:patient_id AS uuid)
        """), {
            "guardian_id": current_user["sub"],
            "patient_id": str(patient.id)
        })
        await db.commit()

        return UserResponse(
            user_id=str(patient.id),
            name=patient.name,
            role=patient.role,
        )


@router.get("/me", response_model=UserResponse)
async def get_me(token_payload: dict = Depends(get_current_user)):
    """내 정보 조회"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, name, role, guardian_id
            FROM users WHERE id = CAST(:id AS uuid)
        """), {"id": token_payload["sub"]})
        user = result.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return UserResponse(
        user_id=str(user.id),
        name=user.name,
        role=user.role,
        guardian_id=str(user.guardian_id) if user.guardian_id else None,
    )