import json
from sqlalchemy import text
from app.database import AsyncSessionLocal
from datetime import date


async def upsert_daily_report(
    patient_id: str,
    slot_result: dict,
) -> None:
    today = date.today()

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, session_count,
                   medication_summary, meal_summary,
                   physical_summary, call_summary
            FROM daily_reports
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND report_date = :today
        """), {"patient_id": patient_id, "today": today})

        existing = result.fetchone()

        # 새 데이터 추출
        new_medications = slot_result.get("medications", [])
        new_meals = slot_result.get("meals", [])
        new_physical = slot_result.get("analysis", {}).get("physical", {})
        new_mood = slot_result.get("analysis", {}).get("mood", {}).get("status")
        new_summary = slot_result.get("call_summary_sections", {})

        if existing:
            # 기존 meals 병합 — 새로 확인된 정보만 업데이트
            existing_meals = existing.meal_summary or []
            if isinstance(existing_meals, str):
                existing_meals = json.loads(existing_meals)
            updated_meals = merge_time_list(existing_meals, new_meals, "time")

            existing_meds = existing.medication_summary or []
            if isinstance(existing_meds, str):
                existing_meds = json.loads(existing_meds)
            updated_meds = merge_time_list(existing_meds, new_medications, "time")

            existing_summary = existing.call_summary or {}
            if isinstance(existing_summary, str):
                existing_summary = json.loads(existing_summary)
            updated_summary = merge_summary(existing_summary, new_summary)

            await db.execute(text("""
                UPDATE daily_reports
                SET medication_summary  = CAST(:medication AS jsonb),
                    meal_summary        = CAST(:meal AS jsonb),
                    physical_summary    = CAST(:physical AS jsonb),
                    mood                = :mood,
                    call_summary        = CAST(:call_summary AS jsonb),
                    session_count       = session_count + 1,
                    last_updated        = NOW()
                WHERE patient_id = CAST(:patient_id AS uuid)
                  AND report_date = :today
            """), {
                "medication": json.dumps(updated_meds, ensure_ascii=False),
                "meal": json.dumps(updated_meals, ensure_ascii=False),
                "physical": json.dumps(new_physical, ensure_ascii=False),
                "mood": new_mood,
                "call_summary": json.dumps(updated_summary, ensure_ascii=False),
                "patient_id": patient_id,
                "today": today,
            })

        else:
            await db.execute(text("""
                INSERT INTO daily_reports
                    (id, patient_id, report_date,
                     medication_summary, meal_summary, physical_summary,
                     mood, call_summary,
                     medication_taken, session_count, last_updated, created_at)
                VALUES
                    (gen_random_uuid(), CAST(:patient_id AS uuid), :today,
                     CAST(:medication AS jsonb),
                     CAST(:meal AS jsonb),
                     CAST(:physical AS jsonb),
                     :mood,
                     CAST(:call_summary AS jsonb),
                     :medication_taken,
                     1, NOW(), NOW())
            """), {
                "patient_id": patient_id,
                "today": today,
                "medication": json.dumps(new_medications, ensure_ascii=False),
                "meal": json.dumps(new_meals, ensure_ascii=False),
                "physical": json.dumps(new_physical, ensure_ascii=False),
                "mood": new_mood,
                "call_summary": json.dumps(new_summary, ensure_ascii=False),
                "medication_taken": any(
                    m.get("taken") for m in new_medications if m.get("taken")
                ),
            })

        await db.commit()


def merge_time_list(existing: list, new: list, key: str) -> list:
    """시간대별 리스트 병합 — 새로 확인된 정보만 업데이트"""
    existing_map = {item.get(key): item for item in existing}
    for item in new:
        time_key = item.get(key)
        if time_key and any(v is not None for k, v in item.items() if k != key):
            existing_map[time_key] = item
    return list(existing_map.values())


def merge_summary(existing: dict, new: dict) -> dict:
    """통화 요약 섹션 병합"""
    result = existing.copy()
    for key, value in new.items():
        if value:
            if result.get(key):
                result[key] = f"{result[key]} / {value}"
            else:
                result[key] = value
    return result