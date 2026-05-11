import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import AsyncSessionLocal
from openai import AsyncOpenAI
from app.config import settings
import uuid

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

async def get_embedding(text_input: str) -> list:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    return response.data[0].embedding

async def test_vector_search():
    async with AsyncSessionLocal() as db:
        # 테스트용 유저 + 세션 먼저 생성
        patient_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        await db.execute(text("""
            INSERT INTO users (id, name, role, profile, created_at)
            VALUES (CAST(:id AS uuid), '테스트환자', 'patient', '{}', NOW())
        """), {"id": patient_id})

        await db.execute(text("""
            INSERT INTO sessions (id, patient_id, call_type, started_at, missed_count, emergency_sent)
            VALUES (CAST(:id AS uuid), CAST(:patient_id AS uuid), 'voluntary', NOW(), 0, false)
        """), {"id": session_id, "patient_id": patient_id})

        await db.commit()

        # 임베딩 생성 + working_memory 저장
        sentences = [
            "어제 딸 민지랑 병원에 다녀왔어요.",
            "오늘 아침에 혈압약 먹었어요.",
            "점심에 갈비탕 먹었어요.",
        ]

        print("임베딩 생성 중...")
        for sentence in sentences:
            embedding = await get_embedding(sentence)
            await db.execute(text("""
                INSERT INTO working_memory (id, session_id, patient_id, speaker, raw_text, embedding, created_at)
                VALUES (gen_random_uuid(), CAST(:session_id AS uuid), CAST(:patient_id AS uuid), 'patient', :text, CAST(:embedding AS vector), NOW())
            """), {
                "session_id": session_id,
                "patient_id": patient_id,
                "text": sentence,
                "embedding": str(embedding),
            })

        await db.commit()
        print("저장 완료!")

        # 검색 테스트
        query = "약 먹었어?"
        print(f"\n검색 쿼리: '{query}'")
        query_embedding = await get_embedding(query)

        result = await db.execute(text("""
            SELECT raw_text,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM working_memory
            WHERE patient_id = CAST(:patient_id AS uuid)
            ORDER BY distance
            LIMIT 3
        """), {"vec": str(query_embedding), "patient_id": patient_id})

        rows = result.fetchall()
        print("\n검색 결과 (유사도 순):")
        for i, row in enumerate(rows):
            print(f"{i+1}. {row.raw_text} (거리: {row.distance:.4f})")

asyncio.run(test_vector_search())