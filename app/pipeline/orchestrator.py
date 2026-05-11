from app.pipeline.stt import transcribe
from app.pipeline.llm import generate_response


async def run_pipeline(
    audio_bytes: bytes,
    conversation_history: list[dict],
    patient_profile: dict,
    rag_context: str | None = None,
) -> dict:
    """STT → LLM 파이프라인"""

    # 1. STT
    raw_text = await transcribe(audio_bytes)

    # 2. LLM
    ai_response = await generate_response(
        utterance=raw_text,
        conversation_history=conversation_history,
        patient_profile=patient_profile,
        rag_context=rag_context,
    )

    return {
        "raw_text": raw_text,
        "ai_response": ai_response,
    }