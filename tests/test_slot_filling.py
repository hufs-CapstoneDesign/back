import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.slot_filling import extract_slot, format_conversation

async def test_slot_filling():
    # orchestrator 테스트에서 나온 대화 히스토리 재현
    conversation_history = [
        {"role": "user", "content": "약을 먹었어. 아까. 흰 거."},
        {"role": "assistant", "content": "아침에 혈압약을 드셨군요. 당뇨약은 드셨나요?"},
        {"role": "user", "content": "저번에 그거 먹었잖아. 혈압약."},
        {"role": "assistant", "content": "네, 아까 아침에 혈압약 드셨죠. 당뇨약은 드셨는지 기억나세요?"},
        {"role": "user", "content": "밥은 먹었어. 갈비탕."},
        {"role": "assistant", "content": "맛있게 드셨군요, 갈비탕."},
    ]

    conversation_text = format_conversation(conversation_history)
    print("=== 대화 원본 ===")
    print(conversation_text)

    print("\n=== Slot Filling 결과 ===")
    result = await extract_slot(conversation_text)

    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(test_slot_filling())