import json
from sqlalchemy import text
from app.database import AsyncSessionLocal
from datetime import datetime, date


async def upsert_daily_report(
    patient_id: str,
    slot_result: dict,
) -> None:
    """
    slot_results → daily_reports upsert
    통화마다 호출, 당일 보고서 누적 갱신
    """
    today = date.today()

    async with AsyncSessionLocal() as db:
        # 오늘 보고서 있는지 확인
        result = await db.execute(text("""
            SELECT id, session_count,
                   medication_summary, meal_summary, status_summary
            FROM daily_reports
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND report_date = :today
        """), {"patient_id": patient_id, "today": today})

        existing = result.fetchone()

        if existing:
            # 기존 보고서 갱신 — 새 통화 데이터 병합
            updated_medication = merge_medication(
                json.loads(existing.medication_summary) if isinstance(existing.medication_summary, str) else existing.medication_summary,
                slot_result.get("medication", {})
            )
            updated_meal = merge_meal(
                json.loads(existing.meal_summary) if isinstance(existing.meal_summary, str) else existing.meal_summary,
                slot_result.get("meal", {})
            )
            updated_status = merge_status(
                json.loads(existing.status_summary) if isinstance(existing.status_summary, str) else existing.status_summary,
                slot_result.get("status", {})
            )

            await db.execute(text("""
                UPDATE daily_reports
                SET medication_summary = CAST(:medication AS jsonb),
                    meal_summary       = CAST(:meal AS jsonb),
                    status_summary     = CAST(:status AS jsonb),
                    session_count      = session_count + 1,
                    last_updated       = NOW()
                WHERE patient_id = CAST(:patient_id AS uuid)
                  AND report_date = :today
            """), {
                "medication": json.dumps(updated_medication, ensure_ascii=False),
                "meal": json.dumps(updated_meal, ensure_ascii=False),
                "status": json.dumps(updated_status, ensure_ascii=False),
                "patient_id": patient_id,
                "today": today,
            })

        else:
            # 오늘 보고서 새로 생성
            await db.execute(text("""
                INSERT INTO daily_reports
                    (id, patient_id, report_date,
                     medication_summary, meal_summary, status_summary,
                     session_count, last_updated)
                VALUES
                    (gen_random_uuid(), CAST(:patient_id AS uuid), :today,
                     CAST(:medication AS jsonb), CAST(:meal AS jsonb), CAST(:status AS jsonb),
                     1, NOW())
            """), {
                "patient_id": patient_id,
                "today": today,
                "medication": json.dumps(slot_result.get("medication", {}), ensure_ascii=False),
                "meal": json.dumps(slot_result.get("meal", {}), ensure_ascii=False),
                "status": json.dumps(slot_result.get("status", {}), ensure_ascii=False),
            })

        await db.commit()


def merge_medication(existing: dict, new: dict) -> dict:
    """복약 정보 병합 — 확인된 정보 우선"""
    if not existing:
        return new
    # taken이 확인되면 유지
    if new.get("taken") is not None:
        existing["taken"] = new["taken"]
    if new.get("drug_name"):
        existing["drug_name"] = new["drug_name"]
    if new.get("time"):
        existing["time"] = new["time"]
    return existing


def merge_meal(existing: dict, new: dict) -> dict:
    """식사 정보 병합 — 메뉴 누적"""
    if not existing:
        return new
    if new.get("eaten") is not None:
        existing["eaten"] = new["eaten"]
    # 메뉴는 누적 (점심 + 저녁)
    if new.get("menu"):
        prev_menu = existing.get("menu", "")
        if prev_menu and new["menu"] not in prev_menu:
            existing["menu"] = f"{prev_menu}, {new['menu']}"
        else:
            existing["menu"] = new["menu"]
    return existing


def merge_status(existing: dict, new: dict) -> dict:
    """상태 정보 병합 — 특이사항 누적"""
    if not existing:
        return new
    if new.get("emotion"):
        existing["emotion"] = new["emotion"]
    if new.get("physical"):
        existing["physical"] = new["physical"]
    # 특이사항 누적
    if new.get("special_note"):
        prev = existing.get("special_note", "")
        if prev:
            existing["special_note"] = f"{prev} / {new['special_note']}"
        else:
            existing["special_note"] = new["special_note"]
    if new.get("flag"):
        existing["flag"] = new["flag"]
    return existing