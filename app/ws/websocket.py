import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

from pipeline.stt import transcribe
from pipeline.orchestrator import run_pipeline


router = APIRouter()

@router.websocket("/ws/calls")
async def voice_websocket(websocket: WebSocket, 
                          session_id: str = Query(...),
                          db: AsyncSession = Depends(get_db)):
    await websocket.accept()

    audio_queue = asyncio.Queue()
    text_queue = asyncio.Queue()

    async def receive_audio():
        """
        클라이언트 -> 서버
        오디오 chunk 수신
        """
        try:
            while True:
                audio_chunk = await websocket.receive_bytes()
                await audio_queue.put(audio_chunk)

        except WebSocketDisconnect:
            print("client disconnected")

    async def call_stt():
        """
        stt 호출 및 오디오 chunk 전달
        전사된 text 수신
        """
        try:
            while True:
                audio_data = await audio_queue.get()
                await text_queue.put(transcribe(audio_data))
                
        except:
            pass

    async def call_pipeline():
        """
        파이프라인 호출 및 필요 parameter 전달
        답변 수신
        """
        raw_text = await text_queue.get()
        

        try:
            while True:
                pass

        except:
            pass    

    async def send_answer():
        pass




    await asyncio.gather(
        receive_audio(),
        call_stt(),
        call_pipeline(),
        send_answer()
    )