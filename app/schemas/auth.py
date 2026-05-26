from pydantic import BaseModel


class SignupRequest(BaseModel):
    username: str  # 아이디
    name: str      # 이름
    phone: str     # 전화번호
    password: str  # 비밀번호
    role: str      # "patient" | "guardian"


class LoginRequest(BaseModel):
    username: str  # 아이디
    password: str  # 비밀번호


class ConnectPatientRequest(BaseModel):
    patient_username: str  # 보호자가 환자 아이디로 연결


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    name: str


class UserResponse(BaseModel):
    user_id: str
    name: str
    role: str
    guardian_id: str | None = None


class FCMTokenRequest(BaseModel):
    fcm_token: str