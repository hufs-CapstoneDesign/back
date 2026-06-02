from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class StartSessionRequest(BaseModel):
    call_type: str


class StartSessionResponse(BaseModel):
    session_id: str
    websocket_url: str


class EndSessionResponse(BaseModel):
    session_id: str
    status: str


class RequestCallResponse(BaseModel):
    success: bool
    message: str