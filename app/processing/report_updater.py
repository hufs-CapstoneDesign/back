# daily_report.py
import json
from sqlalchemy import text
from app.database import AsyncSessionLocal


def empty_medication_slots(medication_times: list[str]) -> list[dict]:
    """시간대 리스트 기반으로 빈 복약 슬롯 생성."""
    return [
        {"time": t, "taken": None, "drug_name": None, "confidence": 0.0}
        for t in medication_times
    ]


async def upsert_daily_report(
    patient_id: str,
    session_id: str,
    slot_result: dict,
    medication_times: list[str],  # parse_medication_times() 결과를 호출부에서 전달
) -> None:
    async with AsyncSessionLocal() as db:
        # Step 1: 세션의 시작 날짜 가져오기
        session_result = await db.execute(text("""
            SELECT DATE(started_at) as session_date
            FROM sessions
            WHERE id = CAST(:session_id AS uuid)
        """), {"session_id": session_id})

        session_row = session_result.fetchone()
        if not session_row:
            print(f"세션을 찾을 수 없습니다: {session_id}")
            return

        report_date = session_row.session_date

        # Step 2: 해당 날짜의 daily_report 조회
        result = await db.execute(text("""
            SELECT id, session_count,
                   medication_summary, meal_summary,
                   physical_summary, call_summary
            FROM daily_reports
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND report_date = :report_date
        """), {"patient_id": patient_id, "report_date": report_date})

        existing = result.fetchone()

        # Step 3: 새 데이터 추출
        new_medications = slot_result.get("medications", [])
        new_meals = slot_result.get("meals", [])
        new_physical = slot_result.get("analysis", {}).get("physical", {})
        new_mood = slot_result.get("analysis", {}).get("mood", {}).get("status")
        new_summary = slot_result.get("call_summary_sections", {})

        if existing:
            # Step 4-1: UPDATE — 기존 데이터와 병합
            existing_meals = existing.meal_summary or []
            if isinstance(existing_meals, str):
                existing_meals = json.loads(existing_meals)
            updated_meals = merge_time_list(existing_meals, new_meals, "time")

            existing_meds = existing.medication_summary or []
            if isinstance(existing_meds, str):
                existing_meds = json.loads(existing_meds)
            # 기존 슬롯이 비어있으면 medication_times 기반으로 초기화 후 병합
            if not existing_meds:
                existing_meds = empty_medication_slots(medication_times)
            updated_meds = merge_time_list(existing_meds, new_medications, "time")

            existing_summary = existing.call_summary or {}
            if isinstance(existing_summary, str):
                existing_summary = json.loads(existing_summary)
            updated_summary = merge_summary_smart(existing_summary, new_summary)

            # medication_taken: 병합된 전체 슬롯 기준으로 재계산
            medication_taken = any(m.get("taken") is True for m in updated_meds)

            await db.execute(text("""
                UPDATE daily_reports
                SET medication_summary  = CAST(:medication AS jsonb),
                    meal_summary        = CAST(:meal AS jsonb),
                    physical_summary    = CAST(:physical AS jsonb),
                    mood                = :mood,
                    call_summary        = CAST(:call_summary AS jsonb),
                    medication_taken    = :medication_taken,
                    session_count       = session_count + 1,
                    last_updated        = NOW()
                WHERE patient_id = CAST(:patient_id AS uuid)
                  AND report_date = :report_date
            """), {
                "medication": json.dumps(updated_meds, ensure_ascii=False),
                "meal": json.dumps(updated_meals, ensure_ascii=False),
                "physical": json.dumps(new_physical, ensure_ascii=False),
                "mood": new_mood,
                "call_summary": json.dumps(updated_summary, ensure_ascii=False),
                "medication_taken": medication_taken,
                "patient_id": patient_id,
                "report_date": report_date,
            })

        else:
            # Step 4-2: INSERT — medication_times 기반 슬롯으로 시작
            # 슬롯 결과가 없는 시간대는 빈 슬롯으로 채움
            slot_map = {m["time"]: m for m in new_medications}
            full_medications = [
                slot_map.get(t, {"time": t, "taken": None, "drug_name": None, "confidence": 0.0})
                for t in medication_times
            ]

            medication_taken = any(m.get("taken") is True for m in full_medications)

            await db.execute(text("""
                INSERT INTO daily_reports
                    (id, patient_id, report_date,
                     medication_summary, meal_summary, physical_summary,
                     mood, call_summary,
                     medication_taken, session_count, last_updated, created_at)
                VALUES
                    (gen_random_uuid(), CAST(:patient_id AS uuid), :report_date,
                     CAST(:medication AS jsonb),
                     CAST(:meal AS jsonb),
                     CAST(:physical AS jsonb),
                     :mood,
                     CAST(:call_summary AS jsonb),
                     :medication_taken,
                     1, NOW(), NOW())
            """), {
                "patient_id": patient_id,
                "report_date": report_date,
                "medication": json.dumps(full_medications, ensure_ascii=False),
                "meal": json.dumps(new_meals, ensure_ascii=False),
                "physical": json.dumps(new_physical, ensure_ascii=False),
                "mood": new_mood,
                "call_summary": json.dumps(new_summary, ensure_ascii=False),
                "medication_taken": medication_taken,
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


def merge_summary_smart(existing: dict, new: dict) -> dict:
    result = existing.copy()
    for key, value in new.items():
        if not value:
            continue
        existing_value = result.get(key, "")
        if not existing_value:
            result[key] = value
        else:
            result[key] = smart_merge_text(existing_value, value)
    return result


def smart_merge_text(existing_text: str, new_text: str) -> str:
    if new_text in existing_text:
        return existing_text
    if existing_text in new_text:
        return new_text
    existing_clean = existing_text.rstrip('.')
    new_clean = new_text.rstrip('.')
    return f"{existing_clean}. {new_clean}."