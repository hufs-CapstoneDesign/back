from openai import AsyncOpenAI
from app.config import settings
from app.prompts.persona import build_system_prompt
from typing import AsyncGenerator

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)


async def generate_response_stream(
    utterance: str,
    conversation_history: list[dict],
    patient_profile: dict,
    rag_context: str | None = None,
    call_type: str = "voluntary",
    ) -> AsyncGenerator[str, None]:
    system_prompt = build_system_prompt(patient_profile, call_type)

    if rag_context:
        system_prompt += f"\n\n[관련 과거 기록]\n{rag_context}"

    messages = [{"role": "system", "content": system_prompt}]
    messages += conversation_history
    messages.append({"role": "user", "content": utterance})

    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=300,
        stream=True,
    )

    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token is not None:
            yield token


def build_system_prompt(patient_profile: dict, rag_context: str | None) -> str:
    name = patient_profile.get("name", "어르신")
    medications = patient_profile.get("medications", [])
    family = patient_profile.get("family", [])

    med_str = ", ".join(medications) if medications else "없음"
    family_str = ", ".join(family) if family else "없음"

    prompt = f"""당신은 치매 어르신을 돌보는 따뜻한 AI 돌봄 파트너입니다.

[환자 정보]
- 이름: {name}
- 복용 중인 약: {med_str}
- 가족: {family_str}

[대화 규칙]
1. 항상 "~해요" 체를 사용하세요.
2. 문장은 짧고 천천히, 한 번에 하나씩만 질문하세요.
3. 환자가 같은 말을 반복해도 자연스럽게 받아주세요.
4. 모르는 정보를 추측하거나 지어내지 마세요.
5. 자연스러운 대화 흐름에서 복약 여부, 식사 여부, 컨디션을 확인하세요."""

    if rag_context:
        prompt += f"\n\n[관련 과거 기록]\n{rag_context}"

    return prompt