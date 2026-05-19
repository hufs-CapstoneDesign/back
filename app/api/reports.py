from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
import json

router = APIRouter(prefix="/reports", tags=["reports"])


def parse_json_field(field):
    """DB에서 가져온 jsonb 필드 파싱"""
    if field is None:
        return None
    if isinstance(field, str):
        try:
            return json.loads(field)
        except json.JSONDecodeError:
            return None
    return field


def build_report_response(row) -> dict:
    """프론트가 원하는 응답 형식으로 변환"""
    
    # DB에서 각 칼럼 파싱
    meals = parse_json_field(row.meal_summary) or []
    medications = parse_json_field(row.medication_summary) or []
    physical = parse_json_field(row.physical_summary) or {}
    call_summary = parse_json_field(row.call_summary) or {}

    # meals가 빈 리스트면 기본 구조 제공
    if not meals:
        meals = [
            {"time": "아침", "eaten": None, "menu": None, "confidence": 0.0},
            {"time": "점심", "eaten": None, "menu": None, "confidence": 0.0},
            {"time": "저녁", "eaten": None, "menu": None, "confidence": 0.0},
        ]

    # medications가 빈 리스트면 기본 구조 제공
    if not medications:
        medications = [
            {"time": "아침", "taken": None, "drug_name": None, "confidence": 0.0},
            {"time": "저녁", "taken": None, "drug_name": None, "confidence": 0.0},
        ]

    # physical이 빈 dict면 기본 구조
    if not physical:
        physical = {"condition": None, "confidence": 0.0}

    # call_summary가 없으면 기본 구조
    if not call_summary:
        call_summary = {
            "health": None,
            "meal": None,
            "emotion": None,
            "daily": None,
        }

    return {
        "id": str(row.id),
        "report_date": str(row.report_date),
        "session_count": row.session_count or 0,
        "last_updated": str(row.last_updated) if row.last_updated else None,
        "meals": meals,
        "medications": medications,
        "analysis": {
            "physical": {
                "condition": physical.get("condition"),
                "confidence": float(physical.get("confidence", 0.0)),
            },
            "mood": {
                "status": row.mood,
                "confidence": 0.92,
            }
        },
        "call_summary_sections": {
            "health": call_summary.get("health"),
            "meal": call_summary.get("meal"),
            "emotion": call_summary.get("emotion"),
            "daily": call_summary.get("daily"),
        }
    }


@router.get("/{patient_id}")
async def get_reports(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """환자의 모든 보고서 조회"""
    result = await db.execute(text("""
        SELECT 
            id, report_date, mood,
            medication_summary, meal_summary,
            physical_summary, call_summary,
            session_count, last_updated
        FROM public.daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
        ORDER BY report_date DESC
        LIMIT 30
    """), {"patient_id": patient_id})

    rows = result.fetchall()
    if not rows:
        return {"reports": []}

    return {"reports": [build_report_response(row) for row in rows]}


from datetime import date as date_type

@router.get("/{patient_id}/{date}")
async def get_report_by_date(
    patient_id: str,
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """특정 날짜의 보고서 조회"""
    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. (예: 2026-05-19)")

    result = await db.execute(text("""
        SELECT 
            id, report_date, mood,
            medication_summary, meal_summary,
            physical_summary, call_summary,
            session_count, last_updated
        FROM public.daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
          AND report_date = :date
    """), {"patient_id": patient_id, "date": report_date})

    row = result.fetchone()

    # 데이터 없으면 빈 기본 구조 반환
    if not row:
        return {
            "id": None,
            "report_date": date,
            "session_count": 0,
            "last_updated": None,
            "meals": [
                {"time": "아침", "eaten": None, "menu": None, "confidence": 0.0},
                {"time": "점심", "eaten": None, "menu": None, "confidence": 0.0},
                {"time": "저녁", "eaten": None, "menu": None, "confidence": 0.0},
            ],
            "medications": [
                {"time": "아침", "taken": None, "drug_name": None, "confidence": 0.0},
                {"time": "저녁", "taken": None, "drug_name": None, "confidence": 0.0},
            ],
            "analysis": {
                "physical": {"condition": None, "confidence": 0.0},
                "mood": {"status": None, "confidence": 0.0}
            },
            "call_summary_sections": {
                "health": None,
                "meal": None,
                "emotion": None,
                "daily": None,
            }
        }

    try:
        return build_report_response(row)
    except Exception as e:
        print(f"보고서 파싱 오류: {e}")
        # 파싱 실패해도 기본 구조 반환
        return {
            "id": str(row.id),
            "report_date": str(row.report_date),
            "session_count": row.session_count or 0,
            "last_updated": str(row.last_updated) if row.last_updated else None,
            "meals": [
                {"time": "아침", "eaten": None, "menu": None, "confidence": 0.0},
                {"time": "점심", "eaten": None, "menu": None, "confidence": 0.0},
                {"time": "저녁", "eaten": None, "menu": None, "confidence": 0.0},
            ],
            "medications": [
                {"time": "아침", "taken": None, "drug_name": None, "confidence": 0.0},
                {"time": "저녁", "taken": None, "drug_name": None, "confidence": 0.0},
            ],
            "analysis": {
                "physical": {"condition": None, "confidence": 0.0},
                "mood": {"status": row.mood, "confidence": 0.0}
            },
            "call_summary_sections": {
                "health": None,
                "meal": None,
                "emotion": None,
                "daily": None,
            }
        }