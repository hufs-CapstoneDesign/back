import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.llm import generate_response

async def test_llm():
    patient_profile = {
        "name": "김영순",
        "medications": ["혈압약", "당뇨약"],
        "family": ["딸 민지", "아들 철수"],
    }

    response = await generate_response(
        utterance="오늘 약 먹었어요",
        conversation_history=[],
        patient_profile=patient_profile,
    )
    print(f"AI 응답: {response}")

asyncio.run(test_llm())