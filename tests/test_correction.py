import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.correction import correct_first_pass

async def test_correction():
    # 치매 환자 비정형 발화 예시들
    test_cases = [
        "약을... 약을 먹었어. 어. 아까. 흰 거. 그거.",
        "음... 밥은 먹었어. 밥은. 아까 먹었다고.",
        "그... 민지가. 민지가 왔었어. 어제.",
    ]

    for utterance in test_cases:
        print(f"\n원본: {utterance}")
        result = await correct_first_pass(utterance)
        print(f"보정: {result['corrected']}")
        print(f"제거: {result['removed']}")
        print(f"신뢰도: {result['confidence']}")

asyncio.run(test_correction())