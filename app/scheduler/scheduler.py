from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from datetime import datetime
from app.database import AsyncSessionLocal
from app.scheduler.fcm import send_call_notification
import uuid

scheduler = AsyncIOScheduler()


async def fire_scheduled_calls():
    """매 분 실행 - 현재 시각/요일에 맞는 스케줄 조회 후 FCM 발신"""
    now = datetime.now()
    current_time = now.strftime("%H:%M:00")
    current_dow = now.weekday()  # 0=월 ... 6=일 (Python 기준)

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT 
                s.id,
                s.patient_id,
                p.fcm_token
            FROM schedules s
            JOIN patients p ON s.patient_id = p.id
            WHERE s.is_active = TRUE
            AND :current_time = s.scheduled_time
            AND :current_dow = ANY(s.days_of_week)
            AND p.fcm_token IS NOT NULL
        """), {
            "current_time": current_time,
            "current_dow": current_dow,
        })

        rows = result.fetchall()

        for row in rows:
            schedule_id = str(row[0])
            patient_id = str(row[1])
            fcm_token = row[2]

            # scheduled_calls 레코드 생성
            scheduled_call_id = str(uuid.uuid4())
            await db.execute(text("""
                INSERT INTO scheduled_calls (id, schedule_id, patient_id, scheduled_at, missed_count, status)
                VALUES (CAST(:id AS uuid), CAST(:schedule_id AS uuid), CAST(:patient_id AS uuid), NOW(), 0, 'pending')
            """), {
                "id": scheduled_call_id,
                "schedule_id": schedule_id,
                "patient_id": patient_id,
            })

            await db.commit()

            # FCM 발신
            try:
                await send_call_notification(fcm_token, patient_id, scheduled_call_id)
                print(f"FCM 발신 완료: patient_id={patient_id}")
            except Exception as e:
                print(f"FCM 발신 실패: {e}")


def start_scheduler():
    scheduler.add_job(
        fire_scheduled_calls,
        CronTrigger(minute="*"),  # 매 분 실행
    )
    scheduler.start()