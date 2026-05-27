import uuid
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.auth import (
    SignupRequest, LoginRequest,
    ConnectPatientRequest, TokenResponse, UserResponse, FCMTokenRequest
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
    요청:
    {
        "basic_info": {
            "name": "김순자",
            "age": 82,
            "guardian_relationship": "자녀",
            "patient_status": "경증",
            "symptoms": ["지남력 장애", "환각"]
        },
        "familyMembers": [
            {"name": "김순미", "relation": "동생"}
        ],
        "contacts": [
            {"name": "김미미", "role": "친구", "nickname": "예삐할머니"}
        ],
        "medication": "하루 2회"
    }
    """
    if current_user["role"] != "guardian":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="보호자만 접근할 수 있습니다.",
        )

    basic_info = request.get("basic_info", {})
    family_members = request.get("familyMembers", [])
    contacts = request.get("contacts", [])
    medication = request.get("medication", "")

    # 필수 값 확인
    if not basic_info.get("name"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="환자 이름은 필수입니다.",
        )

    async with AsyncSessionLocal() as db:
        try:
            # 1. 초대 코드 생성
            invitation_code = str(uuid.uuid4())[:8].upper()
            temp_password = hash_password(invitation_code)
            patient_user_id = str(uuid.uuid4())

            # symptoms 분류 (일단 전부 cognitive_symptoms로 저장)
            symptoms = basic_info.get("symptoms", [])

            # 2. 환자 users 계정 생성
            await db.execute(text("""
                INSERT INTO users (id, username, name, password, role, profile, created_at, updated_at)
                VALUES (
                    CAST(:id AS uuid),
                    :username,
                    :name,
                    :password,
                    'patient',
                    '{}',
                    NOW(), NOW()
                )
            """), {
                "id": patient_user_id,
                "username": f"patient_{patient_user_id[:8]}",
                "name": basic_info["name"],
                "password": temp_password,
            })

            # 3. patients 테이블에 상세 정보 저장
            await db.execute(text("""
                INSERT INTO patients (
                    user_id, age, cognitive_symptoms,
                    medical_notes, created_at, updated_at
                )
                VALUES (
                    CAST(:user_id AS uuid),
                    :age,
                    :symptoms,
                    :medical_notes,
                    NOW(), NOW()
                )
            """), {
                "user_id": patient_user_id,
                "age": basic_info.get("age"),
                "symptoms": symptoms,
                "medical_notes": medication,
            })

            # 4. patient_id 조회
            patient_result = await db.execute(text("""
                SELECT id FROM patients WHERE user_id = CAST(:user_id AS uuid)
            """), {"user_id": patient_user_id})
            patient_id = str(patient_result.fetchone()[0])

            # 5. guardian_id 조회 + relationship 업데이트
            guardian_result = await db.execute(text("""
                SELECT id FROM guardians WHERE user_id = CAST(:user_id AS uuid)
            """), {"user_id": current_user["sub"]})
            guardian_row = guardian_result.fetchone()

            if not guardian_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="보호자 정보를 찾을 수 없습니다.",
                )

            guardian_id = str(guardian_row[0])

            await db.execute(text("""
                UPDATE guardians
                SET relationship = :relationship, updated_at = NOW()
                WHERE user_id = CAST(:user_id AS uuid)
            """), {
                "relationship": basic_info.get("guardian_relationship", ""),
                "user_id": current_user["sub"],
            })

            # 6. patient_guardians 관계 생성
            await db.execute(text("""
                INSERT INTO patient_guardians (
                    patient_id, guardian_id, invitation_code,
                    status, invited_at, accepted_at, created_at, updated_at
                )
                VALUES (
                    CAST(:patient_id AS uuid), CAST(:guardian_id AS uuid),
                    :code, 'accepted', NOW(), NOW(), NOW(), NOW()
                )
            """), {
                "patient_id": patient_id,
                "guardian_id": guardian_id,
                "code": invitation_code,
            })

            # 7. 가족 구성원 caregivers 저장
            for member in family_members:
                if member.get("name"):
                    await db.execute(text("""
                        INSERT INTO caregivers (
                            patient_id, name, role, nickname,
                            created_at, updated_at
                        )
                        VALUES (
                            CAST(:patient_id AS uuid),
                            :name, :role, :nickname,
                            NOW(), NOW()
                        )
                    """), {
                        "patient_id": patient_id,
                        "name": member.get("name", ""),
                        "role": member.get("relation", "가족"),
                        "nickname": member.get("nickname", ""),
                    })

            # 8. 지인/연락처 caregivers 저장
            for contact in contacts:
                if contact.get("name"):
                    await db.execute(text("""
                        INSERT INTO caregivers (
                            patient_id, name, role, nickname,
                            contact_info, created_at, updated_at
                        )
                        VALUES (
                            CAST(:patient_id AS uuid),
                            :name, :role, :nickname,
                            :contact_info,
                            NOW(), NOW()
                        )
                    """), {
                        "patient_id": patient_id,
                        "name": contact.get("name", ""),
                        "role": contact.get("role", "지인"),
                        "nickname": contact.get("nickname", ""),
                        "contact_info": contact.get("contact_info", ""),
                    })

            await db.commit()

            return {
                "patient_id": patient_id,
                "patient_user_id": patient_user_id,
                "invitation_code": invitation_code,
                "message": f"{basic_info['name']}님이 등록되었습니다. 초대코드로 로그인할 수 있습니다."
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


@router.post("/fcm-token")
async def update_fcm_token(
    request: FCMTokenRequest,
    current_user: dict = Depends(get_current_user),
):
    """FCM 토큰 저장 - 로그인 후 호출"""
    fcm_token = request.fcm_token
    if not fcm_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FCM 토큰이 없습니다.",
        )

    async with AsyncSessionLocal() as db:
        try:
            role = current_user["role"]
            user_id = current_user["sub"]

            if role == "patient":
                await db.execute(text("""
                    UPDATE patients
                    SET fcm_token = :fcm_token, updated_at = NOW()
                    WHERE user_id = CAST(:user_id AS uuid)
                """), {"fcm_token": fcm_token, "user_id": user_id})

            elif role == "guardian":
                await db.execute(text("""
                    UPDATE guardians
                    SET fcm_token = :fcm_token, updated_at = NOW()
                    WHERE user_id = CAST(:user_id AS uuid)
                """), {"fcm_token": fcm_token, "user_id": user_id})

            await db.commit()
            return {"status": "ok"}

        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"FCM 토큰 저장 중 오류가 발생했습니다: {str(e)}",
            )