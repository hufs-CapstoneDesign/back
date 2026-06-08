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
    if utterance == "__GREETING__":
        messages.append({"role": "user", "content": "어르신에게 따뜻하게 첫 인사를 건네며 오늘 기분이 어떠신지 물어보며 대화를 시작해줘."})
    else:
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

