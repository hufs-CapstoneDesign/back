import json
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

SLOT_FILLING_PROMPT = """다음은 치매 환자와 AI의 대화입니다.
대화에서 아래 정보를 JSON 형식으로 추출하세요.

[추출 규칙]
1. 대화에서 명확히 언급된 것만 추출하세요.
2. 언급되지 않은 항목은 null로 표시하세요.
3. 절대 추측하거나 지어내지 마세요.
4. source 필드: "direct"(직접 언급) | "inferred"(문맥 추론) | "unknown"(불확실)

[출력 형식] JSON만 출력, 다른 텍스트 없이.
{{
  "medication": {{
    "taken": true | false | null,
    "drug_name": "약 이름 또는 null",
    "time": "복용 시간 또는 null",
    "source": "direct | inferred | unknown"
  }},
  "meal": {{
    "eaten": true | false | null,
    "menu": "메뉴 또는 null",
    "time": "식사 시간 또는 null",
    "source": "direct | inferred | unknown"
  }},
  "status": {{
    "emotion": "감정 상태 한 줄 또는 null",
    "physical": "신체 상태 한 줄 또는 null",
    "special_note": "특이사항 또는 null",
    "flag": "이상징후 또는 null"
  }},
  "confidence": 0.0 ~ 1.0
}}

[대화]
{conversation}
"""

async def extract_slot(conversation: str) -> dict:
    """
    통화 종료 후 대화 전체에서 Slot Filling
    복약/식사/상태 JSON 추출
    """
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": SLOT_FILLING_PROMPT.format(conversation=conversation)
            }
        ],
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    return result


def format_conversation(history: list[dict]) -> str:
    """대화 히스토리를 텍스트로 변환"""
    lines = []
    for turn in history:
        role = "환자" if turn["role"] == "user" else "AI"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)