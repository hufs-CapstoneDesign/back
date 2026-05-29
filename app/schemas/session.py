from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    patient_id: str
    call_type: str

class RequestCallRequest(BaseModel):
    patient_id: str