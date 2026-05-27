from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date as date_type
import json

from app.database import get_db
from app.api.deps import get_current_user
from app.api.conversations import resolve_patient_id

router = APIRouter(prefix="/reports", tags=["reports"])


def parse_json_field(field):
    if field is None:
        return None
    if isinstance(field, str):
        return json.loads(field)
    return field


def build_report_response(row) -> dict:
    meals = parse_json_field(row.meal_summary) or []
    medications = parse_json_field(row.medication_summary) or []
    physical = parse_json_field(row.physical_summary) or {}
    call_summary = parse_json_field(row.call_summary) or {}

    if not meals:
        meals = [
            {"time": "아침", "eaten": None, "menu": None, "confidence": 0.0},
            {"time": "점심", "eaten": None, "menu": None, "confidence": 0.0},
            {"time": "저녁", "eaten": None, "menu": None, "confidence": 0.0},
        ]

    if not medications:
        medications = [
            {"time": "아침", "taken": None, "drug_name": None, "confidence": 0.0},
            {"time": "저녁", "taken": None, "drug_name": None, "confidence": 0.0},
        ]

    return {
        "id": str(row.id),
        "report_date": str(row.report_date),
        "session_count": row.session_count,
        "last_updated": str(row.last_updated),
        "meals": meals,
        "medications": medications,
        "analysis": {
            "physical": {
                "condition": physical.get("condition"),
                "confidence": physical.get("confidence", 0.0),
            },
            "mood": {
                "status": row.mood,
                "confidence": 0.8,
            }
        },
        "call_summary_sections": {
            "health": call_summary.get("health"),
            "meal": call_summary.get("meal"),
            "emotion": call_summary.get("emotion"),
            "daily": call_summary.get("daily"),
        }
    }


def empty_report(date: str) -> dict:
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


@router.get("")
async def get_reports(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """보고서 목록 조회 (최근 30일)"""
    user_id = current_user["sub"]
    role = current_user["role"]
    patient_id = await resolve_patient_id(user_id, role, db)

    result = await db.execute(text("""
        SELECT 
            id, report_date, mood,
            medication_summary, meal_summary,
            physical_summary, call_summary,
            session_count, last_updated
        FROM daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
        ORDER BY report_date DESC
        LIMIT 30
    """), {"patient_id": patient_id})

    rows = result.fetchall()
    if not rows:
        return {"reports": []}

    reports = []
    for row in rows:
        try:
            reports.append(build_report_response(row))
        except Exception as e:
            print(f"보고서 파싱 오류: {e}")
            continue

    return {"reports": reports}


@router.get("/{date}")
async def get_report_by_date(
    date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """특정 날짜 보고서 조회"""
    user_id = current_user["sub"]
    role = current_user["role"]
    patient_id = await resolve_patient_id(user_id, role, db)

    try:
        report_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="날짜 형식이 올바르지 않습니다. (예: 2026-05-18)"
        )

    result = await db.execute(text("""
        SELECT 
            id, report_date, mood,
            medication_summary, meal_summary,
            physical_summary, call_summary,
            session_count, last_updated
        FROM daily_reports
        WHERE patient_id = CAST(:patient_id AS uuid)
          AND report_date = :date
    """), {"patient_id": patient_id, "date": report_date})

    row = result.fetchone()

    if not row:
        return empty_report(date)

    try:
        return build_report_response(row)
    except Exception as e:
        print(f"보고서 파싱 오류: {e}")
        return empty_report(date)