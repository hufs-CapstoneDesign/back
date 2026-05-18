import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.pipeline.stt import transcribe
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.tts import generate_tts
from app.pipeline.rag import save_to_working_memory, save_to_messages
from app.processing.post_call import process_after_call
from app.utils.audio import convert_to_wav

router = APIRouter(tags=["ws"])

SILENCE_TIMEOUT = 3


async def get_patient_info(session_id: str, db: AsyncSession) -> dict:
    session_result = await db.execute(text("""
        SELECT patient_id, call_type FROM sessions 
        WHERE id = CAST(:session_id AS uuid)
    """), {"session_id": session_id})

    session_row = session_result.fetchone()
    if not session_row:
        raise ValueError(f"세션을 찾을 수 없습니다: {session_id}")

    patient_id = session_row[0]
    call_type = session_row[1] or "voluntary"  # 기본값

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
        "cognitive_symptoms": patient_row[4] or [],
        "behavioral_symptoms": patient_row[5] or [],
        "medical_notes": patient_row[6],
        "call_type": call_type,  # 추가
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
    stop_event = asyncio.Event()
    pipeline_done_event = asyncio.Event()  # 배치 처리 완료 신호

    patient_profile = await get_patient_info(session_id, db)
    patient_id = patient_profile.pop("patient_id")
    call_type = patient_profile.pop("call_type")
    print(f"call_type: {call_type}")

    conversation_history = []

    async def receive_audio():
        try:
            while True:
                audio_chunk = await websocket.receive_bytes()
                wav_bytes = convert_to_wav(audio_chunk)
                await audio_queue.put(wav_bytes)
        except WebSocketDisconnect:
            print("클라이언트 연결 종료")
        finally:
            stop_event.set()
            # 파이프라인 완료 대기 (최대 60초)
            try:
                await asyncio.wait_for(pipeline_done_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                print("배치 처리 타임아웃")

    async def call_stt():
        try:
            while not stop_event.is_set():
                try:
                    audio_data = await asyncio.wait_for(
                        audio_queue.get(), timeout=1.0
                    )
                    text = await transcribe(audio_data)
                    if text:
                        await text_queue.put(text)
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            print(f"STT 오류: {e}")

    async def call_pipeline():
        accumulated_text = ""

        while not stop_event.is_set():
            try:
                text = await asyncio.wait_for(
                    text_queue.get(), timeout=SILENCE_TIMEOUT
                )
                accumulated_text += " " + text

            except asyncio.TimeoutError:
                if not accumulated_text.strip():
                    continue

                raw_text = accumulated_text.strip()
                print(f"파이프라인 실행: {raw_text}")

                try:
                    result = await run_pipeline(
                        raw_text=raw_text,
                        session_id=session_id,
                        patient_id=patient_id,
                        conversation_history=conversation_history,
                        patient_profile=patient_profile,
                        call_type=call_type,
                    )

                    await save_to_messages(
                        session_id=session_id,
                        patient_id=patient_id,
                        sender_type="patient",
                        content=raw_text,
                        corrected_content=result["corrected_text"],
                    )
                    await save_to_messages(
                        session_id=session_id,
                        patient_id=patient_id,
                        sender_type="ai",
                        content=result["ai_response"],
                    )

                    await save_to_working_memory(
                        session_id=session_id,
                        patient_id=patient_id,
                        speaker="patient",
                        raw_text=result["corrected_text"],
                    )
                    await save_to_working_memory(
                        session_id=session_id,
                        patient_id=patient_id,
                        speaker="ai",
                        raw_text=result["ai_response"],
                    )

                    conversation_history.append({
                        "role": "user",
                        "content": result["corrected_text"],
                    })
                    conversation_history.append({
                        "role": "assistant",
                        "content": result["ai_response"],
                    })

                    print("생성된 답변: ", result["ai_response"])
                    audio_bytes = await generate_tts(result["ai_response"])
                    await websocket.send_bytes(audio_bytes)
                    await websocket.send_text("END")

                except Exception as e:
                    print(f"파이프라인 오류: {e}")
                finally:
                    accumulated_text = ""

        # 통화 종료 후 배치 처리
        print("통화 종료 — 배치 처리 시작")
        try:
            if conversation_history:
                await process_after_call(
                    session_id=session_id,
                    patient_id=patient_id,
                    conversation_history=conversation_history,
                )
                print("배치 처리 완료")
            else:
                print("대화 내역 없음 — 배치 처리 생략")
        except Exception as e:
            print(f"배치 처리 오류: {e}")
        finally:
            pipeline_done_event.set()  # 배치 처리 완료 신호

    await asyncio.gather(
        receive_audio(),
        call_stt(),
        call_pipeline(),
    )