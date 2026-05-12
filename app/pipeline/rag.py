from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

# RAG 트리거 키워드
TRIGGER_KEYWORDS = [
    "저번에", "그거", "아까", "거기", "지난번",
    "어제", "전에", "그때", "그분", "그사람",
    "거기서", "저기", "요전에", "지지난"
]

async def get_embedding(text_input: str) -> list:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    return response.data[0].embedding


def should_trigger_rag(utterance: str) -> bool:
    """트리거 키워드 감지"""
    return any(kw in utterance for kw in TRIGGER_KEYWORDS)


async def search_working_memory(
    query_embedding: list,
    session_id: str,
    limit: int = 2,
) -> list[str]:
    """현재 통화 내 유사 발화 검색"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT raw_text,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM working_memory
            WHERE session_id = CAST(:session_id AS uuid)
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
    """환자 장기 기억 검색"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT content,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM long_term_memory
            WHERE patient_id = CAST(:patient_id AS uuid)
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
    """
    RAG 트리거 감지 후 컨텍스트 검색
    working_memory → long_term_memory 순서로 검색
    """
    if not should_trigger_rag(utterance):
        return None

    query_embedding = await get_embedding(utterance)

    # 1. 현재 통화 내 검색
    wm_results = await search_working_memory(query_embedding, session_id)

    # 2. 장기 기억 검색
    ltm_results = await search_long_term_memory(query_embedding, patient_id)

    # 결과 없으면 None
    if not wm_results and not ltm_results:
        return None

    # 컨텍스트 조합
    context_parts = []
    for r in wm_results:
        context_parts.append(f"[현재 통화] {r}")
    for r in ltm_results:
        context_parts.append(f"[과거 기록] {r}")

    return "\n".join(context_parts)

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
                (id, session_id, patient_id, speaker, raw_text, embedding, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid), CAST(:patient_id AS uuid),
                 :speaker, :raw_text, CAST(:embedding AS vector), NOW())
        """), {
            "session_id": session_id,
            "patient_id": patient_id,
            "speaker": speaker,
            "raw_text": raw_text,
            "embedding": str(embedding),
        })
        await db.commit()