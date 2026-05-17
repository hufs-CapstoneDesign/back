from app.processing.slot_filling import (
    extract_slot, save_slot_result, format_conversation
)
from app.processing.consolidation import consolidate_to_long_term
from app.processing.report_updater import upsert_daily_report
from app.pipeline.rag import save_to_messages


async def process_after_call(
    session_id: str,
    patient_id: str,
    conversation_history: list[dict],
) -> dict:
    """
    통화 종료 후 배치 처리 통합
    1. messages 테이블 저장 확인
    2. Slot Filling → slot_results 저장
    3. Long-term Memory 이관
    4. 일간 보고서 갱신
    """
    conversation_text = format_conversation(conversation_history)

    print("[배치] Slot Filling 시작...")
    slot_result = await extract_slot(conversation_text)
    await save_slot_result(
        session_id=session_id,
        patient_id=patient_id,
        slot_result=slot_result,
    )
    print(f"[배치] Slot Filling 완료")

    print("[배치] Long-term Memory 이관 시작...")
    facts = await consolidate_to_long_term(
        session_id=session_id,
        patient_id=patient_id,
        conversation=conversation_text,
    )
    print(f"[배치] Long-term Memory {len(facts)}개 저장 완료")

    print("[배치] 보고서 갱신 시작...")
    await upsert_daily_report(
        patient_id=patient_id,
        slot_result=slot_result,
    )
    print("[배치] 보고서 갱신 완료")

    return {
        "slot_result": slot_result,
        "facts_count": len(facts),
    }