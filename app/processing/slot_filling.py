# slot_filling.py
import json
from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

_SLOT_FILLING_PROMPT_TEMPLATE = """다음은 치매 환자와 AI의 대화입니다.
대화에서 아래 정보를 JSON 형식으로 추출하세요.

[추출 규칙 - 반드시 준수]
1. 대화에서 환자가 직접 언급한 것만 추출하세요.
2. 언급되지 않은 항목은 반드시 null로 표시하세요.
3. 절대 추측하거나 지어내지 마세요. AI의 질문에 환자가 답하지 않았다면 null입니다.
4. [confidence 산정 기준 — 반드시 준수]
- 환자가 명확하고 일관되게 말했을 때만 0.9 이상
- "~한 것 같아", "~인가?", "~었나?" 등 불확실 표현이 있으면 최대 0.6
- 대화 중 번복(예: "안 먹었어" → "먹었어")이 있으면 최대 0.55
- 불확실 표현 + 번복이 모두 있으면 최대 0.45
- 언급 없으면 0.0
5. 복약은 {medication_times_desc} 기준입니다.
6. 식사는 아침/점심/저녁 3끼 기준입니다.
7. "taken: null"은 대화에서 해당 시간대 복약을 확인하지 못한 것입니다. false와 다릅니다.
8. AI가 복약을 물어봤는데 환자가 답하지 않은 경우도 null입니다.
9. 식사 메뉴는 menu_candidates 배열에 저장하며, 확실성 여부를 menu_certain 플래그로 표시합니다.
- 환자가 먹었다고 언급한 메뉴가 특정 메뉴로 확실하면 menu_candidates에 해당 메뉴명을 넣고 menu_certain은 true로 하세요. (예: "미역국 먹었어" -> menu_candidates: ["미역국"], menu_certain: true)
- 메뉴를 여러 개 언급하거나 번복/불확실(예: "빵 하나 먹었나? 피자 먹은 것 같기도 하고...")하면 menu_candidates에 모든 후보를 배열로 넣고 menu_certain은 false로 하세요. (예: menu_candidates: ["빵", "피자"], menu_certain: false)
- 식사 언급이 전혀 없거나 메뉴를 모르는 경우 menu_candidates는 빈 배열 []로 하고 menu_certain은 true로 하세요.
10. call_summary_sections 작성 기준:
- 환자의 발화를 그대로 반영하세요.
- "~한 것 같아", "~인가?" 등 불확실 표현이 있으면 요약에도 반드시 불확실성을 포함하세요.
  예) "먹은 것 같다고 말함" (O) / "먹었다고 언급함" (X)
- 번복이 있었던 경우: "처음에는 X라고 했다가 Y로 번복함"처럼 번복 사실을 명시하세요.

[출력 형식] JSON만 출력, 다른 텍스트 없이.
{{
  "meals": [
    {{"time": "아침", "eaten": true | false | null, "menu_candidates": ["메뉴후보"], "menu_certain": true | false, "confidence": 0.0}},
    {{"time": "점심", "eaten": true | false | null, "menu_candidates": ["메뉴후보"], "menu_certain": true | false, "confidence": 0.0}},
    {{"time": "저녁", "eaten": true | false | null, "menu_candidates": ["메뉴후보"], "menu_certain": true | false, "confidence": 0.0}}
  ],
  "medications": [
{medication_slots}
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

[판단 예시]
- 환자가 "약 먹었어"라고 했다면 → taken: true, confidence: 0.95
- AI가 "약 드셨나요?" 물었는데 환자가 다른 말을 했다면 → taken: null, confidence: 0.0
- 대화에서 저녁 약 언급이 전혀 없다면 → 저녁 taken: null, confidence: 0.0

[대화]
{conversation}
"""


def build_slot_filling_prompt(conversation: str, medication_times: list[str]) -> str:
    """medication_times 기반으로 프롬프트의 복약 슬롯을 동적 생성."""
    slots = "\n".join(
        f'    {{"time": "{t}", "taken": true | false | null, "drug_name": "약 이름 또는 null", "confidence": 0.0}}'
        for t in medication_times
    )
    times_desc = "/".join(medication_times) + f" {len(medication_times)}회"

    return _SLOT_FILLING_PROMPT_TEMPLATE.format(
        medication_times_desc=times_desc,
        medication_slots=slots,
        conversation=conversation,
    )


def compute_avg_confidence(slot_result: dict) -> float:
    """슬롯 결과 전체에서 언급된 항목의 평균 confidence 계산."""
    scores = []
    for m in slot_result.get("medications", []):
        scores.append(m.get("confidence", 0.0))
    for m in slot_result.get("meals", []):
        scores.append(m.get("confidence", 0.0))
    physical_conf = slot_result.get("analysis", {}).get("physical", {}).get("confidence", 0.0)
    mood_conf = slot_result.get("analysis", {}).get("mood", {}).get("confidence", 0.0)
    scores.extend([physical_conf, mood_conf])
    non_zero = [s for s in scores if s > 0.0]
    return round(sum(non_zero) / len(non_zero), 3) if non_zero else 0.0


async def extract_slot(conversation: str, medication_times: list[str]) -> dict:
    prompt = build_slot_filling_prompt(conversation, medication_times)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
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
            "confidence": compute_avg_confidence(slot_result),
            "source": "direct",
        })
        await db.commit()


def format_conversation(history: list[dict]) -> str:
    lines = []
    for turn in history:
        role = "환자" if turn["role"] == "user" else "AI"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)