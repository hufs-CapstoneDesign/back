from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

TRIGGER_KEYWORDS = [
    "저번에", "그거", "아까", "거기", "지난번",
    "어제", "전에", "그때", "그분", "그사람",
    "거기서", "저기", "요전에", "지지난",
    "아들", "딸", "가족", "언제", "깜빡", "잊어버렸",
    "뭐였지", "기억", "뭐라고", "했었나", "했나"
]


async def get_embedding(text_input: str) -> list:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    return response.data[0].embedding


def should_trigger_rag(utterance: str) -> bool:
    return any(kw in utterance for kw in TRIGGER_KEYWORDS)


async def save_to_working_memory(
    session_id: str,
    patient_id: str,
    speaker: str,
    raw_text: str,
) -> None:
    """발화마다 working_memory에 저장 + 임베딩"""
    embedding = await get_embedding(raw_text)

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO working_memory
                (id, session_id, patient_id, speaker, raw_text,
                 memory_content, embedding, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid),
                 CAST(:patient_id AS uuid), :speaker, :raw_text,
                 :raw_text, CAST(:embedding AS vector), NOW())
        """), {
            "session_id": session_id,
            "patient_id": patient_id,
            "speaker": speaker,
            "raw_text": raw_text,
            "embedding": str(embedding),
        })
        await db.commit()


async def save_to_messages(
    session_id: str,
    patient_id: str,
    sender_type: str,
    content: str,
    corrected_content: str | None = None,
) -> None:
    """messages 테이블에 대화 원본 저장"""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO messages
                (id, session_id, patient_id, sender_type,
                 content, corrected_content, message_type, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid),
                 CAST(:patient_id AS uuid), :sender_type,
                 :content, :corrected_content, 'text', NOW())
        """), {
            "session_id": session_id,
            "patient_id": patient_id,
            "sender_type": sender_type,
            "content": content,
            "corrected_content": corrected_content,
        })
        await db.commit()


async def search_working_memory(
    query_embedding: list,
    session_id: str,
    limit: int = 2,
) -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT raw_text,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM working_memory
            WHERE session_id = CAST(:session_id AS uuid)
              AND embedding IS NOT NULL
            ORDER BY distance
            LIMIT :limit
        """), {
            "vec": str(query_embedding),
            "session_id": session_id,
            "limit": limit,
        })
        rows = result.fetchall()
        return [row.raw_text for row in rows if row.distance < 0.7]


async def search_long_term_memory(
    query_embedding: list,
    patient_id: str,
    limit: int = 3,
) -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT content,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM long_term_memory
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND embedding IS NOT NULL
            ORDER BY distance
            LIMIT :limit
        """), {
            "vec": str(query_embedding),
            "patient_id": patient_id,
            "limit": limit,
        })
        rows = result.fetchall()
        return [row.content for row in rows if row.distance < 0.7]


async def retrieve_context(
    utterance: str,
    session_id: str,
    patient_id: str,
) -> str | None:
    query_embedding = await get_embedding(utterance)

    # working_memory는 트리거 있을 때만
    wm_results = []
    if should_trigger_rag(utterance):
        wm_results = await search_working_memory(query_embedding, session_id)

    # long_term_memory는 항상 검색 (개인 정보 기반 응답)
    ltm_results = await search_long_term_memory(query_embedding, patient_id)

    if not wm_results and not ltm_results:
        return None

    context_parts = []
    for r in wm_results:
        context_parts.append(f"[현재 통화] {r}")
    for r in ltm_results:
        context_parts.append(f"[과거 기록] {r}")

    return "\n".join(context_parts)