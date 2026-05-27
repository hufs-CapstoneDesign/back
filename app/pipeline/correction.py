from openai import AsyncOpenAI
from app.config import settings
from app.pipeline.confidence import calculate_confidence

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

CORRECTION_SECOND_PROMPT = """당신은 치매 환자의 발화에서 지시어를 해소하는 어시스턴트입니다.

[규칙]
1. "그거", "저거", "거기", "그분" 같은 지시어를 아래 환자 정보와 대화 맥락을 참고해서 실제 의미로 바꾸세요.
2. 확실하지 않으면 [불명확] 태그를 붙이세요. 절대 추측하지 마세요.
3. 지시어 외의 내용은 건드리지 마세요.

[출력 형식] JSON만 출력, 다른 텍스트 없이.
{{
  "normalized": "지시어가 해소된 텍스트",
  "resolved": {{"원래 지시어": "해소된 의미"}},
  "confidence": 0.0 ~ 1.0
}}

[환자 정보]
{patient_info}

[직전 대화 맥락]
{context}

[보정할 발화]
{utterance}
"""

async def correct_second_pass(
    corrected_text: str,
    patient_profile: dict,
    conversation_history: list[dict],
    rag_context: str | None = None,
) -> dict:
    """
    2차 발화 보정 (배치)
    지시어 해소 — RAG + 환자 정보 활용
    """
    # 환자 정보 포맷
    patient_info = f"""
- 이름: {patient_profile.get('name', '미상')}
- 복용약: {', '.join(patient_profile.get('medications', []))}
- 가족: {', '.join(patient_profile.get('family', []))}
""".strip()

    # 직전 3턴 대화 맥락
    recent = conversation_history[-6:] if len(conversation_history) >= 6 else conversation_history
    context_lines = []
    for turn in recent:
        role = "환자" if turn["role"] == "user" else "AI"
        context_lines.append(f"{role}: {turn['content']}")

    if rag_context:
        context_lines.append(f"\n[과거 기록]\n{rag_context}")

    context = "\n".join(context_lines) if context_lines else "없음"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": CORRECTION_SECOND_PROMPT.format(
                    patient_info=patient_info,
                    context=context,
                    utterance=corrected_text,
                )
            }
        ],
        max_tokens=200,
        response_format={"type": "json_object"},
    )

    import json
    result = json.loads(response.choices[0].message.content)
    final_confidence = calculate_confidence(
    llm_confidence=result.get("confidence", 0.5),
    utterance=corrected_text,
    rag_used=rag_context is not None,
    rag_hit=rag_context is not None and len(rag_context) > 20,
    context_found=len(conversation_history) > 0,
    profile_match=len(patient_profile.get("medications", [])) > 0,
    )

    result["llm_confidence"] = result.get("confidence", 0.5)
    result["confidence"] = final_confidence

    return result