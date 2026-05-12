import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.post_call import process_after_call

async def test_post_call():
    patient_id = "43f1ea1d-d684-4181-a2d3-6b695f9061cf"
    session_id = "a640b857-9d91-4192-9868-04f5948b2712"

    conversation_history = [
        {"role": "user", "content": "약을 먹었어. 아까. 혈압약."},
        {"role": "assistant", "content": "혈압약 드셨군요. 당뇨약은요?"},
        {"role": "user", "content": "당뇨약도 먹었어. 노란 거."},
        {"role": "assistant", "content": "두 가지 다 드셨군요. 식사는요?"},
        {"role": "user", "content": "밥은 먹었어. 갈비탕."},
        {"role": "assistant", "content": "갈비탕 드셨군요. 오늘 기분은 어떠세요?"},
        {"role": "user", "content": "기분 좋아. 민지가 오늘 온대."},
        {"role": "assistant", "content": "민지 씨가 오신다니 좋겠네요."},
    ]

    print("=== 통화 종료 후 배치 처리 시작 ===\n")
    result = await process_after_call(
        session_id=session_id,
        patient_id=patient_id,
        conversation_history=conversation_history,
    )

    print(f"\n=== 최종 결과 ===")
    print(f"Slot 추출: {result['slot_result']}")
    print(f"저장된 사실: {result['facts_count']}개")
    print("\n✅ 통화 종료 후 처리 완료!")

asyncio.run(test_post_call())