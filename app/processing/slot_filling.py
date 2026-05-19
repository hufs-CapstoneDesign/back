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
4. confidence: 0.0~1.0 (확실하면 1.0, 불확실하면 낮게)
5. 복약은 아침/저녁 2회 기준입니다.
6. 식사는 아침/점심/저녁 3끼 기준입니다.

[출력 형식] JSON만 출력, 다른 텍스트 없이.
{{
  "meals": [
    {{"time": "아침", "eaten": true | false | null, "menu": "메뉴 또는 null", "confidence": 0.0}},
    {{"time": "점심", "eaten": true | false | null, "menu": "메뉴 또는 null", "confidence": 0.0}},
    {{"time": "저녁", "eaten": true | false | null, "menu": "메뉴 또는 null", "confidence": 0.0}}
  ],
  "medications": [
    {{"time": "아침", "taken": true | false | null, "drug_name": "약 이름 또는 null", "confidence": 0.0}},
    {{"time": "저녁", "taken": true | false | null, "drug_name": "약 이름 또는 null", "confidence": 0.0}}
  ],
  "analysis": {{
    "physical": {{"condition": "신체 상태 한 줄 또는 null", "confidence": 0.0}},
    "mood": {{"status": "감정 상태 한 줄 또는 null", "confidence": 0.0}}
  }},
  "call_summary_sections": {{
    "health": "신체적 건강, 복약 관련 내용 또는 null",
    "meal": "식사 및 메뉴 관련 내용 또는 null",
    "emotion": "정서, 감정 관련 내용 또는 null",
    "daily": "위 세 항목에 포함되지 않은 일상/기타 내용 또는 null"
  }}
}}

[대화]
{conversation}
"""


async def extract_slot(conversation: str) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": SLOT_FILLING_PROMPT.format(conversation=conversation)
            }
        ],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


async def save_slot_result(
    session_id: str,
    patient_id: str,
    slot_result: dict,
) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO slot_results
                (id, patient_id, session_id,
                 medication, meal, physical,
                 emotion, call_summary,
                 confidence_score, source, created_at)
            VALUES
                (gen_random_uuid(),
                 CAST(:patient_id AS uuid),
                 CAST(:session_id AS uuid),
                 CAST(:medication AS jsonb),
                 CAST(:meal AS jsonb),
                 CAST(:physical AS jsonb),
                 :emotion,
                 :call_summary,
                 :confidence,
                 :source,
                 NOW())
        """), {
            "patient_id": patient_id,
            "session_id": session_id,
            "medication": json.dumps(slot_result.get("medications", []), ensure_ascii=False),
            "meal": json.dumps(slot_result.get("meals", []), ensure_ascii=False),
            "physical": json.dumps(slot_result.get("analysis", {}).get("physical", {}), ensure_ascii=False),
            "emotion": slot_result.get("analysis", {}).get("mood", {}).get("status"),
            "call_summary": json.dumps(slot_result.get("call_summary_sections", {}), ensure_ascii=False),
            "confidence": 0.8,
            "source": "direct",
        })
        await db.commit()


def format_conversation(history: list[dict]) -> str:
    lines = []
    for turn in history:
        role = "환자" if turn["role"] == "user" else "AI"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)