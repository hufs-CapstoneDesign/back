import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.report_updater import upsert_daily_report
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def test_report_updater():
    patient_id = "43f1ea1d-d684-4181-a2d3-6b695f9061cf"

    # 1차 통화 결과
    slot_result_1 = {
        "medication": {"taken": True, "drug_name": "혈압약", "time": "아침", "source": "direct"},
        "meal": {"eaten": True, "menu": "갈비탕", "time": None, "source": "direct"},
        "status": {"emotion": None, "physical": None, "special_note": None, "flag": None},
        "confidence": 1.0
    }

    print("=== 1차 통화 보고서 생성 ===")
    await upsert_daily_report(patient_id=patient_id, slot_result=slot_result_1)
    print("✅ 1차 저장 완료")

    # 2차 통화 결과 (저녁 추가)
    slot_result_2 = {
        "medication": {"taken": True, "drug_name": "당뇨약", "time": "저녁", "source": "direct"},
        "meal": {"eaten": True, "menu": "된장찌개", "time": "저녁", "source": "direct"},
        "status": {"emotion": "평온함", "physical": None, "special_note": None, "flag": None},
        "confidence": 0.9
    }

    print("\n=== 2차 통화 보고서 갱신 ===")
    await upsert_daily_report(patient_id=patient_id, slot_result=slot_result_2)
    print("✅ 2차 갱신 완료")

    # 결과 확인
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT report_date, medication_summary, meal_summary,
                   status_summary, session_count, last_updated
            FROM daily_reports
            WHERE patient_id = CAST(:patient_id AS uuid)
            ORDER BY report_date DESC
            LIMIT 1
        """), {"patient_id": patient_id})
        row = result.fetchone()

    if row:
        print(f"\n=== 최종 보고서 ===")
        print(f"날짜: {row.report_date}")
        print(f"통화 횟수: {row.session_count}")
        print(f"복약: {row.medication_summary}")
        print(f"식사: {row.meal_summary}")
        print(f"상태: {row.status_summary}")
        print(f"마지막 갱신: {row.last_updated}")

asyncio.run(test_report_updater())