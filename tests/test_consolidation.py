import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.consolidation import consolidate_to_long_term
from app.processing.slot_filling import format_conversation

async def test_consolidation():
    # 어제 생성된 ID
    patient_id = "43f1ea1d-d684-4181-a2d3-6b695f9061cf"
    session_id = "a640b857-9d91-4192-9868-04f5948b2712"

    conversation_history = [
        {"role": "user", "content": "약을 먹었어. 아까. 흰 거."},
        {"role": "assistant", "content": "혈압약 드셨군요. 당뇨약은요?"},
        {"role": "user", "content": "저번에 그거 먹었잖아. 혈압약."},
        {"role": "assistant", "content": "네, 아침에 혈압약 드셨죠."},
        {"role": "user", "content": "밥은 먹었어. 갈비탕."},
        {"role": "assistant", "content": "갈비탕 드셨군요."},
    ]

    conversation_text = format_conversation(conversation_history)

    print("=== Long-term Memory 이관 시작 ===")
    facts = await consolidate_to_long_term(
        session_id=session_id,
        patient_id=patient_id,
        conversation=conversation_text,
    )

    print(f"\n추출된 사실 {len(facts)}개:")
    for i, fact in enumerate(facts):
        print(f"\n{i+1}. {fact['content']}")
        print(f"   메타데이터: {fact['metadata']}")

    print("\n✅ long_term_memory 저장 완료!")
    print("DBeaver에서 확인: SELECT * FROM long_term_memory;")

asyncio.run(test_consolidation())