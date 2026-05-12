import json
from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
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

async def save_slot_result(session_id: str, slot_result: dict) -> None:
    """추출된 Slot 결과를 slot_results 테이블에 저장"""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO slot_results
                (id, session_id, medication, meal, status, confidence, source, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid),
                 CAST(:medication AS jsonb), CAST(:meal AS jsonb), CAST(:status AS jsonb),
                 :confidence, :source, NOW())
        """), {
            "session_id": session_id,
            "medication": json.dumps(slot_result.get("medication", {}), ensure_ascii=False),
            "meal": json.dumps(slot_result.get("meal", {}), ensure_ascii=False),
            "status": json.dumps(slot_result.get("status", {}), ensure_ascii=False),
            "confidence": slot_result.get("confidence", 0.0),
            "source": slot_result.get("medication", {}).get("source", "unknown"),
        })
        await db.commit()

def format_conversation(history: list[dict]) -> str:
    """대화 히스토리를 텍스트로 변환"""
    lines = []
    for turn in history:
        role = "환자" if turn["role"] == "user" else "AI"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)