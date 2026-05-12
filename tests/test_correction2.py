import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.correction import correct_second_pass

async def test_second_pass():
    patient_profile = {
        "name": "김영순",
        "medications": ["혈압약(흰색)", "당뇨약(노란색)"],
        "family": ["딸 민지", "아들 철수"],
    }

    conversation_history = [
        {"role": "assistant", "content": "오늘 약 드셨나요?"},
        {"role": "user", "content": "약을 먹었어. 아까. 흰 거."},
        {"role": "assistant", "content": "혈압약 드셨군요. 당뇨약은요?"},
    ]

    test_cases = [
        "흰 거 먹었어. 아까.",
        "민지가 사다 준 그거 먹었어.",
        "거기 다녀왔어. 어제.",
        "그분이 왔었어.",
    ]

    for utterance in test_cases:
        print(f"\n원본: {utterance}")
        result = await correct_second_pass(
            corrected_text=utterance,
            patient_profile=patient_profile,
            conversation_history=conversation_history,
        )
        print(f"해소: {result['normalized']}")
        print(f"지시어 매핑: {result['resolved']}")
        print(f"신뢰도: {result['confidence']}")

asyncio.run(test_second_pass())