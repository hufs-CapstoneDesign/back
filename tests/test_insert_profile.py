import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.processing.consolidation import get_embedding
import json

PATIENT_ID = "6d3ef730-2ac9-4290-8db2-31859bcc49a5"

profile_data = [
    ("family_info", "아들 이름은 김철수", "profile", 95),
    ("family_info", "아들이 이번 주 토요일 점심에 방문 예정", "profile", 90),
    ("medication", "약은 하루에 1번, 오전 8시에 복용", "profile", 95),
    ("medication", "아침 약은 4알", "profile", 85),
    ("health_condition", "날짜와 시간을 자주 헷갈려함", "profile", 90),
    ("personal_item", "어제 무릎에 붙인 파스", "profile", 60),
    ("health_precaution", "계단 내려갈 때 난간을 꼭 잡아야 함", "profile", 85),
]

async def insert_profile():
    async with AsyncSessionLocal() as db:
        for memory_type, content, source, confidence in profile_data:
            embedding = await get_embedding(content)
            await db.execute(text("""
                INSERT INTO long_term_memory
                    (id, patient_id, memory_type, memory_content,
                     content, embedding, source, confidence_score, created_at)
                VALUES
                    (gen_random_uuid(), CAST(:patient_id AS uuid),
                     :memory_type, :content,
                     :content, CAST(:embedding AS vector),
                     :source, :confidence, NOW())
            """), {
                "patient_id": PATIENT_ID,
                "memory_type": memory_type,
                "content": content,
                "embedding": str(embedding),
                "source": source,
                "confidence": confidence,
            })
            print(f"✅ 저장: {content}")

        await db.commit()
        print("\n모든 프로필 데이터 저장 완료!")

asyncio.run(insert_profile())