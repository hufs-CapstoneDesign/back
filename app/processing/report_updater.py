import json
from sqlalchemy import text
from app.database import AsyncSessionLocal
from datetime import date, datetime


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

        if existing:
            updated_medication = merge_dict(
                existing.medication_summary or {},
                slot_result.get("medication", {})
            )
            updated_meal = merge_meal(
                existing.meal_summary or {},
                slot_result.get("meal", {})
            )
            updated_physical = merge_dict(
                existing.physical_summary or {},
                slot_result.get("physical", {})
            )

            await db.execute(text("""
                UPDATE daily_reports
                SET medication_summary  = CAST(:medication AS jsonb),
                    meal_summary        = CAST(:meal AS jsonb),
                    physical_summary    = CAST(:physical AS jsonb),
                    mood                = :emotion,
                    call_summary        = :call_summary,
                    session_count       = session_count + 1,
                    last_updated        = NOW()
                WHERE patient_id = CAST(:patient_id AS uuid)
                  AND report_date = :today
            """), {
                "medication": json.dumps(updated_medication, ensure_ascii=False),
                "meal": json.dumps(updated_meal, ensure_ascii=False),
                "physical": json.dumps(updated_physical, ensure_ascii=False),
                "emotion": slot_result.get("emotion"),
                "call_summary": slot_result.get("call_summary"),
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
                     :emotion, :call_summary,
                     :medication_taken,
                     1, NOW(), NOW())
            """), {
                "patient_id": patient_id,
                "today": today,
                "medication": json.dumps(slot_result.get("medication", {}), ensure_ascii=False),
                "meal": json.dumps(slot_result.get("meal", {}), ensure_ascii=False),
                "physical": json.dumps(slot_result.get("physical", {}), ensure_ascii=False),
                "emotion": slot_result.get("emotion"),
                "call_summary": slot_result.get("call_summary"),
                "medication_taken": slot_result.get("medication", {}).get("taken"),
            })

        await db.commit()


def merge_dict(existing: dict, new: dict) -> dict:
    if not existing:
        return new
    for key, value in new.items():
        if value is not None:
            existing[key] = value
    return existing


def merge_meal(existing: dict, new: dict) -> dict:
    if not existing:
        return new
    if new.get("eaten") is not None:
        existing["eaten"] = new["eaten"]
    if new.get("menu"):
        prev = existing.get("menu", "")
        if prev and new["menu"] not in prev:
            existing["menu"] = f"{prev}, {new['menu']}"
        else:
            existing["menu"] = new["menu"]
    return existing