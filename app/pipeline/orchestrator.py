from app.pipeline.correction import correct_first_pass
from app.pipeline.rag import retrieve_context
from app.pipeline.llm import generate_response


async def run_pipeline(
    raw_text: str,
    session_id: str,
    patient_id: str,
    conversation_history: list[dict],
    patient_profile: dict,
    call_type: str = "voluntary",
) -> dict:
    # 1. 1차 발화 보정
    correction_result = await correct_first_pass(raw_text)
    corrected_text = correction_result["corrected"]

    # 2. RAG 검색
    rag_context = await retrieve_context(
        utterance=corrected_text,
        session_id=session_id,
        patient_id=patient_id,
    )

    # 3. LLM 답변 생성
    ai_response = await generate_response(
        utterance=corrected_text,
        conversation_history=conversation_history,
        patient_profile=patient_profile,
        rag_context=rag_context,
        call_type=call_type,
    )

    return {
        "raw_text": raw_text,
        "corrected_text": corrected_text,
        "rag_used": rag_context is not None,
        "rag_context": rag_context,
        "ai_response": ai_response,
    }