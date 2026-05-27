import json
from sqlalchemy import text
from app.database import AsyncSessionLocal
from datetime import date


async def upsert_daily_report(
    patient_id: str,
    session_id: str,
    slot_result: dict,
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
            # Step 4-1: 기존 데이터가 있으면 UPDATE
            # 기존 meals 병합
            existing_meals = existing.meal_summary or []
            if isinstance(existing_meals, str):
                existing_meals = json.loads(existing_meals)
            updated_meals = merge_time_list(existing_meals, new_meals, "time")

            # 기존 medications 병합
            existing_meds = existing.medication_summary or []
            if isinstance(existing_meds, str):
                existing_meds = json.loads(existing_meds)
            updated_meds = merge_time_list(existing_meds, new_medications, "time")

            # 기존 call_summary 병합 (스마트하게)
            existing_summary = existing.call_summary or {}
            if isinstance(existing_summary, str):
                existing_summary = json.loads(existing_summary)
            updated_summary = merge_summary_smart(existing_summary, new_summary)

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
                  AND report_date = :report_date
            """), {
                "medication": json.dumps(updated_meds, ensure_ascii=False),
                "meal": json.dumps(updated_meals, ensure_ascii=False),
                "physical": json.dumps(new_physical, ensure_ascii=False),
                "mood": new_mood,
                "call_summary": json.dumps(updated_summary, ensure_ascii=False),
                "patient_id": patient_id,
                "report_date": report_date,
            })

        else:
            # Step 4-2: 기존 데이터가 없으면 INSERT
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


def merge_summary_smart(existing: dict, new: dict) -> dict:
    """
    통화 요약 섹션 스마트 병합 - 중복 제거
    
    예시:
    기존: "아침은 전복죽을 드셨습니다."
    신규: "아침은 전복죽을 드셨습니다."
    결과: "아침은 전복죽을 드셨습니다." (중복 제거)
    
    예시:
    기존: "아침은 전복죽을 드셨습니다."
    신규: "점심은 미역국을 드셨습니다."
    결과: "아침은 전복죽을 드셨습니다. 점심은 미역국을 드셨습니다." (병합)
    """
    result = existing.copy()
    
    for key, value in new.items():
        if not value:  # 새 값이 없으면 스킵
            continue
        
        existing_value = result.get(key, "")
        
        if not existing_value:  # 기존 값이 없으면 새 값으로 설정
            result[key] = value
        else:
            # 기존 값과 새 값이 모두 있으면 스마트하게 병합
            result[key] = smart_merge_text(existing_value, value)
    
    return result


def smart_merge_text(existing_text: str, new_text: str) -> str:
    """
    두 텍스트를 스마트하게 병합 - 중복 문장 제거
    
    예시:
    기존: "아침은 전복죽을 드셨으나 점심은 입맛이 없다며 거르셨습니다."
    신규: "아침은 전복죽을 드셨습니다."
    결과: "아침은 전복죽을 드셨으나 점심은 입맛이 없다며 거르셨습니다."
          (신규 내용이 기존에 이미 포함되어 있으므로 중복 제거)
    """
    
    # 기존 텍스트에 새 텍스트가 이미 포함되어 있으면 그냥 반환
    if new_text in existing_text:
        return existing_text
    
    # 새 텍스트에 기존 텍스트가 이미 포함되어 있으면 새 텍스트만 사용
    # (더 상세한 정보가 들어온 경우)
    if existing_text in new_text:
        return new_text
    
    # 둘 다 새로운 정보면 합치기
    # 마침표 처리
    existing_clean = existing_text.rstrip('.')
    new_clean = new_text.rstrip('.')
    
    # 띄어쓰기로 구분하여 병합
    merged = f"{existing_clean}. {new_clean}."
    
    return merged