from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

CORRECTION_PROMPT = """당신은 치매 환자의 발화를 보정하는 어시스턴트입니다.
아래 규칙에 따라 입력된 발화를 보정하세요.

[규칙]
1. 반복된 단어나 문장은 1회로 정규화하세요.
2. "어...", "음...", "그..." 같은 필러(filler)는 제거하세요.
3. 문장 중간의 "..." 같은 끊김 표시는 제거하세요.
4. 의미를 추가하거나 추측하지 마세요. 있는 그대로만 정리하세요.
5. "그거", "저거", "거기" 같은 지시어는 그대로 두세요. (2차 보정에서 처리)

[출력 형식]
JSON만 출력하세요. 다른 텍스트 없이.
{
  "corrected": "보정된 텍스트",
  "removed": ["제거된 항목 목록"],
  "confidence": 0.0 ~ 1.0
}

[입력 발화]
"""

async def correct_first_pass(raw_text: str) -> dict:
    """
    1차 발화 보정 (실시간)
    반복·필러 제거만 빠르게 처리
    """
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": CORRECTION_PROMPT + raw_text
            }
        ],
        max_tokens=200,
        response_format={"type": "json_object"},
    )

    import json
    result = json.loads(response.choices[0].message.content)
    return result