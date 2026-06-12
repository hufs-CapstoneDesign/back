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

            # physical_summary 병합: 새로운 정보가 유효하면(condition이 null이 아니고 신뢰도가 기존 이상이거나 기존 condition이 null인 경우) 업데이트
            existing_physical = existing.physical_summary or {}
            if isinstance(existing_physical, str):
                existing_physical = json.loads(existing_physical)
            
            if new_physical.get("condition") is not None:
                old_conf = existing_physical.get("confidence", 0.0)
                new_conf = new_physical.get("confidence", 0.0)
                if existing_physical.get("condition") is None or new_conf >= old_conf:
                    updated_physical = new_physical
                else:
                    updated_physical = existing_physical
            else:
                updated_physical = existing_physical

            # mood 병합: 새로운 mood status가 존재하고 신뢰도(0.0보다 큼)가 있는 경우 업데이트
            existing_mood = existing.mood
            new_mood_status = slot_result.get("analysis", {}).get("mood", {}).get("status")
            new_mood_conf = slot_result.get("analysis", {}).get("mood", {}).get("confidence", 0.0)
            
            if new_mood_status is not None and new_mood_conf > 0.0:
                updated_mood = new_mood_status
            else:
                updated_mood = existing_mood if existing_mood else new_mood_status

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
                "physical": json.dumps(updated_physical, ensure_ascii=False),
                "mood": updated_mood,
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
    """시간대별 리스트 병합 — 정보가 있는 경우에만 기존 신뢰도와 비교해 업데이트"""
    existing_map = {item.get(key): item.copy() for item in existing}
    
    for item in new:
        time_key = item.get(key)
        if not time_key:
            continue
        
        # 신규 아이템에 실질적인 정보(식사 여부 혹은 복약 여부)가 있는지 판별
        new_val = item.get("eaten") if "eaten" in item else item.get("taken")
        new_conf = item.get("confidence", 0.0)
        
        if time_key in existing_map:
            old_item = existing_map[time_key]
            old_val = old_item.get("eaten") if "eaten" in old_item else old_item.get("taken")
            old_conf = old_item.get("confidence", 0.0)
            
            # 새 정보가 유효한 경우 (None이 아님)
            if new_val is not None:
                # 기존 값이 없었거나, 새 정보의 신뢰도가 기존 신뢰도보다 크거나 같을 때 갱신
                if old_val is None or new_conf >= old_conf:
                    merged_item = item.copy()
                    if "menu_candidates" in item:
                        old_candidates = old_item.get("menu_candidates", [])
                        new_candidates = item.get("menu_candidates", [])
                        merged_candidates = list(dict.fromkeys(old_candidates + new_candidates))
                        merged_item["menu_candidates"] = merged_candidates
                        
                        if not old_item.get("menu_certain", True) or not item.get("menu_certain", True):
                            merged_item["menu_certain"] = False
                            
                    existing_map[time_key] = merged_item
                else:
                    # 기존 정보 신뢰도가 더 높은 경우에도 식사 메뉴 후보가 추가로 들어왔다면 누적
                    if "menu_candidates" in item:
                        old_candidates = old_item.get("menu_candidates", [])
                        new_candidates = item.get("menu_candidates", [])
                        merged_candidates = list(dict.fromkeys(old_candidates + new_candidates))
                        old_item["menu_candidates"] = merged_candidates
                        if not item.get("menu_certain", True):
                            old_item["menu_certain"] = False
            else:
                # 새 정보의 eaten/taken이 None이지만, 메뉴 후보가 새로 들어왔다면 누적
                if "menu_candidates" in item and item.get("menu_candidates"):
                    old_candidates = old_item.get("menu_candidates", [])
                    new_candidates = item.get("menu_candidates", [])
                    merged_candidates = list(dict.fromkeys(old_candidates + new_candidates))
                    old_item["menu_candidates"] = merged_candidates
                    if not item.get("menu_certain", True):
                        old_item["menu_certain"] = False
        else:
            # 기존에 없던 시간대면 그냥 추가
            existing_map[time_key] = item.copy()
            
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