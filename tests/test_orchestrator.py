import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.orchestrator import run_pipeline

async def test_orchestrator():
    patient_profile = {
        "name": "김영순",
        "medications": ["혈압약", "당뇨약"],
        "family": ["딸 민지", "아들 철수"],
    }

    # 어제 생성된 ID
    patient_id = "43f1ea1d-d684-4181-a2d3-6b695f9061cf"
    session_id = "a640b857-9d91-4192-9868-04f5948b2712"

    test_cases = [
        "약을... 약을 먹었어. 어. 아까. 흰 거.",
        "저번에 그거 먹었잖아. 혈압약.",
        "밥은 먹었어. 갈비탕.",
    ]

    conversation_history = []

    for utterance in test_cases:
        print(f"\n{'='*50}")
        print(f"환자 발화: {utterance}")

        result = await run_pipeline(
            raw_text=utterance,
            session_id=session_id,
            patient_id=patient_id,
            conversation_history=conversation_history,
            patient_profile=patient_profile,
        )

        print(f"보정된 텍스트: {result['corrected_text']}")
        print(f"RAG 사용: {result['rag_used']}")
        if result['rag_context']:
            print(f"RAG 컨텍스트: {result['rag_context']}")
        print(f"AI 응답: {result['ai_response']}")

        # 대화 히스토리 누적
        conversation_history.append({"role": "user", "content": result["corrected_text"]})
        conversation_history.append({"role": "assistant", "content": result["ai_response"]})

asyncio.run(test_orchestrator())