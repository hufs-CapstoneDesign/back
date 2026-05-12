import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.rag import should_trigger_rag, retrieve_context

async def test_rag():
    # 트리거 감지 테스트
    print("=== 트리거 감지 테스트 ===")
    test_cases = [
        ("오늘 약 먹었어요", False),
        ("저번에 민지가 사다 준 거 있잖아", True),
        ("어제 병원 다녀왔어", True),
        ("밥 먹었어요", False),
        ("그거 어디다 뒀지", True),
    ]

    for utterance, expected in test_cases:
        result = should_trigger_rag(utterance)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{utterance}' → 트리거: {result}")

    # 실제 DB 검색 테스트 (어제 넣은 데이터 활용)
    print("\n=== RAG 검색 테스트 ===")
    # 어제 test_rag.py에서 생성된 patient_id, session_id 사용
    # DBeaver에서 확인해서 넣어줘
    patient_id = "43f1ea1d-d684-4181-a2d3-6b695f9061cf"
    session_id = "a640b857-9d91-4192-9868-04f5948b2712"

    result = await retrieve_context(
        utterance="저번에 약 먹었던 거 있잖아",
        session_id=session_id,
        patient_id=patient_id,
    )
    print(f"검색 결과:\n{result}")

asyncio.run(test_rag())