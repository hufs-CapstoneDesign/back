import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
#from app.pipeline.stt import transcribe
from app.pipeline.orchestrator import run_pipeline

router = APIRouter(tags=["ws"])

SILENCE_TIMEOUT = 3  # 초 단위, 이 시간동안 추가 텍스트 없으면 파이프라인 실행


async def transcribe(audio_data):
    print(f"audio size: {len(audio_data)}")
    return "안녕하세요 테스트입니다"




async def get_patient_info(session_id: str, db: AsyncSession) -> dict:
    # 1. session_id로 patient_id 조회
    session_result = await db.execute(text("""
        SELECT patient_id FROM sessions WHERE id = CAST(:session_id AS uuid)
    """), {"session_id": session_id})
    
    session_row = session_result.fetchone()
    if not session_row:
        raise ValueError(f"세션을 찾을 수 없습니다: {session_id}")
    
    patient_id = session_row[0]

    # 2. patient_id로 환자 정보 조회
    patient_result = await db.execute(text("""
        SELECT 
            p.id,
            u.name,
            p.birth_date,
            p.age,
            p.cognitive_symptoms,
            p.behavioral_symptoms,
            p.medical_notes
        FROM patients p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = CAST(:patient_id AS uuid)
    """), {"patient_id": str(patient_id)})

    patient_row = patient_result.fetchone()
    if not patient_row:
        raise ValueError(f"환자 정보를 찾을 수 없습니다: {patient_id}")

    return {
        "patient_id": str(patient_row[0]),
        "name": patient_row[1],
        "birth_date": str(patient_row[2]) if patient_row[2] else None,
        "age": patient_row[3],
        "cognitive_symptoms": patient_row[4],
        "behavioral_symptoms": patient_row[5],
        "medical_notes": patient_row[6],
    }

@router.websocket("/ws/calls")
async def voice_websocket(
    websocket: WebSocket,
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    await websocket.accept()

    audio_queue = asyncio.Queue()
    text_queue = asyncio.Queue()
    stop_event = asyncio.Event()  # 연결 종료 신호
    patient_profile = await get_patient_info(session_id, db)
    patient_id = patient_profile.pop("patient_id")

    async def receive_audio():
        try:
            while True:
                audio_chunk = await websocket.receive_bytes()
                await audio_queue.put(audio_chunk)
        except WebSocketDisconnect:
            print("client disconnected")
        finally:
            stop_event.set()  # 연결 끊기면 다른 태스크도 종료

    async def call_stt():
        try:
            while not stop_event.is_set():
                try:
                    audio_data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    text = await transcribe(audio_data)  # transcribe가 sync면 run_in_executor 필요
                    if text:
                        await text_queue.put(text)
                except asyncio.TimeoutError:
                    continue  # 큐에 데이터 없으면 계속 대기
        except Exception as e:
            print(f"STT 오류: {e}")

    async def call_pipeline():
        """
        text_queue에서 텍스트를 모으다가
        SILENCE_TIMEOUT 동안 추가 입력 없으면 파이프라인 실행
        """
        accumulated_text = ""

        while not stop_event.is_set():
            try:
                # SILENCE_TIMEOUT 안에 새 텍스트가 오면 계속 누적
                text = await asyncio.wait_for(text_queue.get(), timeout=SILENCE_TIMEOUT)
                accumulated_text += " " + text

            except asyncio.TimeoutError:
                # timeout 동안 추가 입력 없음 → 파이프라인 실행
                if not accumulated_text.strip():
                    continue  # 누적된 텍스트 없으면 그냥 대기

                print(f"파이프라인 실행: {accumulated_text.strip()}")
                try:
                    result = await run_pipeline(
                        raw_text=accumulated_text.strip(),
                        session_id=session_id,
                        patient_id=patient_id,
                        conversation_history=[],
                        patient_profile=patient_profile,
                    )
                    # 클라이언트에 응답 전송(LLM까지의 동작을 보기 위한 임시 response)
                    await websocket.send_json({
                        "type": "answer",
                        "text": result["ai_response"],
                        "corrected_text": result["corrected_text"],
                        "rag_used": result["rag_used"],
                    })
                except Exception as e:
                    print(f"파이프라인 오류: {e}")
                finally:
                    accumulated_text = ""  # 누적 텍스트 초기화

    await asyncio.gather(
        receive_audio(),
        call_stt(),
        call_pipeline(),
    )