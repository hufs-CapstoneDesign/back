import json
from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

CONSOLIDATION_PROMPT = """다음은 치매 환자와 AI의 한 통화 대화입니다.
이 대화에서 장기 기억으로 저장할 핵심 사실을 추출하세요.

[규칙]
1. 각 사실을 하나의 완성된 문장으로 작성하세요.
2. 오늘 날짜를 포함하세요: {date}
3. 최대 5개 항목만 추출하세요.
4. 대화에서 언급된 사실만 적으세요. 추측 금지.

[출력 형식] JSON만 출력, 다른 텍스트 없이.
{{
  "facts": [
    {{
      "content": "2026-05-12(월), 아침에 혈압약 복용 완료.",
      "metadata": {{
        "who": [],
        "place": null,
        "topic": "혈압약",
        "emotion": null
      }}
    }}
  ]
}}

[대화]
{conversation}
"""

async def get_embedding(text_input: str) -> list:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    return response.data[0].embedding


async def consolidate_to_long_term(
    session_id: str,
    patient_id: str,
    conversation: str,
) -> list[dict]:
    """
    통화 종료 후 Long-term Memory 이관
    대화 → LLM 사실 추출 → 임베딩 → long_term_memory 저장
    """
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d(%a)")

    # LLM으로 핵심 사실 추출
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": CONSOLIDATION_PROMPT.format(
                    date=today,
                    conversation=conversation,
                )
            }
        ],
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    facts = result.get("facts", [])

    async with AsyncSessionLocal() as db:
        for fact in facts:
            # 임베딩 생성
            embedding = await get_embedding(fact["content"])

            # long_term_memory 저장
            await db.execute(text("""
                INSERT INTO long_term_memory
                    (id, patient_id, source_session_id, content, embedding, metadata, created_at)
                VALUES
                    (gen_random_uuid(), CAST(:patient_id AS uuid), CAST(:session_id AS uuid),
                     :content, CAST(:embedding AS vector), CAST(:metadata AS jsonb), NOW())
            """), {
                "patient_id": patient_id,
                "session_id": session_id,
                "content": fact["content"],
                "embedding": str(embedding),
                "metadata": json.dumps(fact["metadata"], ensure_ascii=False),
            })

        await db.commit()

    return facts