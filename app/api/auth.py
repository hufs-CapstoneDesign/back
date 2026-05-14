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
    """회원가입 - patients/guardians 테이블에 데이터 저장"""
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
                INSERT INTO users (id, username, name, phone, password, role, profile, created_at, updated_at)
                VALUES (CAST(:id AS uuid), :username, :name, :phone, :password, :role, '{}', NOW(), NOW())
            """), {
                "id": user_id,
                "username": request.username,
                "name": request.name,
                "phone": request.phone,
                "password": hashed_pw,
                "role": request.role,
            })

            # role에 따라 patients 또는 guardians 테이블에 추가 정보 저장
            if request.role == "patient":
                # 환자 정보 저장
                await db.execute(text("""
                    INSERT INTO patients (user_id, created_at, updated_at)
                    VALUES (CAST(:user_id AS uuid), NOW(), NOW())
                """), {"user_id": user_id})
            
            elif request.role == "guardian":
                # 보호자 정보 저장
                await db.execute(text("""
                    INSERT INTO guardians (user_id, created_at, updated_at)
                    VALUES (CAST(:user_id AS uuid), NOW(), NOW())
                """), {"user_id": user_id})

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


@router.post("/invite-patient", response_model=dict)
async def invite_patient(
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    보호자가 새로운 환자를 초대
    요청: {
        "patient_name": "김순자",
        "patient_phone": "010-9999-8888",
        "birth_date": "1953-01-01",
        "age": 71,
        "cognitive_symptoms": ["기억력 장애"],
        "behavioral_symptoms": ["오인"],
        "relationship": "자녀"
    }
    """
    # 보호자만 호출 가능
    if current_user["role"] != "guardian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="보호자만 접근할 수 있습니다.",
        )
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. 환자용 임시 계정 생성
            patient_user_id = str(uuid.uuid4())
            # 임시 비밀번호 생성 (초대코드와 동일)
            invitation_code = str(uuid.uuid4())[:8].upper()
            temp_password = hash_password(invitation_code)

            await db.execute(text("""
                INSERT INTO users (id, username, name, phone, password, role, profile, created_at, updated_at)
                VALUES (CAST(:id AS uuid), :username, :name, :phone, :password, :role, '{}', NOW(), NOW())
            """), {
                "id": patient_user_id,
                "username": f"temp_{patient_user_id[:8]}",
                "name": request.get("patient_name", ""),
                "phone": request.get("patient_phone", ""),
                "password": temp_password,
                "role": "patient",
            })

            # 2. 환자 상세 정보 저장
            await db.execute(text("""
                INSERT INTO patients (user_id, birth_date, age, cognitive_symptoms, behavioral_symptoms, created_at, updated_at)
                VALUES (
                    CAST(:user_id AS uuid),
                    CAST(:birth_date AS date),
                    :age,
                    :cognitive_symptoms,
                    :behavioral_symptoms,
                    NOW(),
                    NOW()
                )
            """), {
                "user_id": patient_user_id,
                "birth_date": request.get("birth_date"),
                "age": request.get("age"),
                "cognitive_symptoms": request.get("cognitive_symptoms"),
                "behavioral_symptoms": request.get("behavioral_symptoms"),
            })

            # 3. 보호자 정보 업데이트
            await db.execute(text("""
                UPDATE guardians 
                SET relationship = :relationship, updated_at = NOW()
                WHERE user_id = CAST(:guardian_user_id AS uuid)
            """), {
                "relationship": request.get("relationship", ""),
                "guardian_user_id": current_user["sub"],
            })

            # 4. patient_id와 guardian_id 조회
            patient_result = await db.execute(text("""
                SELECT id FROM patients WHERE user_id = CAST(:user_id AS uuid)
            """), {"user_id": patient_user_id})
            patient_id = patient_result.fetchone()[0]

            guardian_result = await db.execute(text("""
                SELECT id FROM guardians WHERE user_id = CAST(:user_id AS uuid)
            """), {"user_id": current_user["sub"]})
            guardian_id = guardian_result.fetchone()[0]

            # 5. patient_guardians 관계 생성
            await db.execute(text("""
                INSERT INTO patient_guardians (patient_id, guardian_id, invitation_code, status, invited_at, accepted_at, created_at, updated_at)
                VALUES (CAST(:patient_id AS uuid), CAST(:guardian_id AS uuid), :code, 'accepted', NOW(), NOW(), NOW(), NOW())
            """), {
                "patient_id": str(patient_id),
                "guardian_id": str(guardian_id),
                "code": invitation_code,
            })

            await db.commit()

            return {
                "patient_user_id": patient_user_id,
                "invitation_code": invitation_code,
                "message": "환자가 성공적으로 등록되었습니다. 환자는 이 초대코드로 로그인할 수 있습니다."
            }

        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            print(f"환자 초대 에러: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"환자 등록 중 오류가 발생했습니다: {str(e)}",
            )


@router.post("/login-with-code", response_model=TokenResponse)
async def login_with_code(request: dict):
    """
    환자가 초대코드로 로그인/가입
    요청: {
        "invitation_code": "ABC123XYZ"
    }
    """
    invitation_code = request.get("invitation_code")
    
    async with AsyncSessionLocal() as db:
        try:
            # 초대코드로 patient_guardian 조회
            result = await db.execute(text("""
                SELECT pg.patient_id, pg.guardian_id, p.user_id
                FROM patient_guardians pg
                JOIN patients p ON pg.patient_id = p.id
                WHERE pg.invitation_code = :code AND pg.status = 'accepted'
            """), {"code": invitation_code})
            
            pg_row = result.fetchone()
            
            if not pg_row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="유효하지 않은 초대코드입니다.",
                )
            
            patient_user_id = pg_row[2]
            
            # 환자 정보 조회
            user_result = await db.execute(text("""
                SELECT id, name, role FROM users WHERE id = CAST(:id AS uuid)
            """), {"id": str(patient_user_id)})
            
            user = user_result.fetchone()
            
            token = create_access_token(user_id=str(user.id), role=user.role)
            return TokenResponse(
                access_token=token,
                token_type="bearer",
                user_id=str(user.id),
                role=user.role,
                name=user.name,
            )
        
        except HTTPException:
            raise
        except Exception as e:
            print(f"초대코드 로그인 에러: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"로그인 중 오류가 발생했습니다: {str(e)}",
            )


@router.post("/connect-patient", response_model=UserResponse)
async def connect_patient(
    request: ConnectPatientRequest,
    current_user: dict = Depends(get_current_user)
):
    """보호자가 기존 환자 username으로 연결"""
    # 보호자만 호출 가능
    if current_user["role"] != "guardian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="보호자만 접근할 수 있습니다.",
        )
    
    async with AsyncSessionLocal() as db:
        try:
            # 환자 조회
            result = await db.execute(text("""
                SELECT u.id, u.name, u.role, p.id as patient_id
                FROM users u
                JOIN patients p ON u.id = p.user_id
                WHERE u.username = :username AND u.role = 'patient'
            """), {"username": request.patient_username})
            
            patient_row = result.fetchone()

            if not patient_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="해당 아이디의 환자를 찾을 수 없습니다.",
                )
            
            patient_user_id = patient_row[0]
            patient_id = patient_row[3]
            
            # 보호자 정보 조회
            guardian_result = await db.execute(text("""
                SELECT id FROM guardians WHERE user_id = CAST(:guardian_user_id AS uuid)
            """), {"guardian_user_id": current_user["sub"]})
            guardian_row = guardian_result.fetchone()
            
            if not guardian_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="보호자 정보를 찾을 수 없습니다.",
                )
            
            guardian_id = guardian_row[0]
            
            # 이미 존재하는 관계인지 확인
            existing = await db.execute(text("""
                SELECT id FROM patient_guardians 
                WHERE patient_id = CAST(:patient_id AS uuid) 
                AND guardian_id = CAST(:guardian_id AS uuid)
            """), {
                "patient_id": str(patient_id),
                "guardian_id": str(guardian_id),
            })
            
            if existing.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="이미 연결된 환자입니다.",
                )
            
            # 새로운 초대코드 생성
            new_invitation_code = str(uuid.uuid4())[:8].upper()
            
            # patient_guardians에 관계 추가
            await db.execute(text("""
                INSERT INTO patient_guardians (patient_id, guardian_id, invitation_code, status, invited_at, accepted_at, created_at, updated_at)
                VALUES (CAST(:patient_id AS uuid), CAST(:guardian_id AS uuid), :code, 'accepted', NOW(), NOW(), NOW(), NOW())
            """), {
                "patient_id": str(patient_id),
                "guardian_id": str(guardian_id),
                "code": new_invitation_code,
            })
            
            await db.commit()

            return UserResponse(
                user_id=str(patient_user_id),
                name=patient_row[1],
                role=patient_row[2],
            )
        
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            print(f"환자 연결 에러: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"환자 연결 중 오류가 발생했습니다: {str(e)}",
            )


@router.get("/me", response_model=UserResponse)
async def get_me(token_payload: dict = Depends(get_current_user)):
    """내 정보 조회"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, name, role FROM users WHERE id = CAST(:id AS uuid)
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
        guardian_id=None,
    )