from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import text
from datetime import datetime, timedelta
from app.database import AsyncSessionLocal
from app.fcm.fcm import send_call_notification, send_missed_call_notification
import uuid

scheduler = AsyncIOScheduler()
minutes=5


async def check_missed_call(scheduled_call_id: str, patient_id: str, fcm_token: str, guardian_fcm_token: str, patient_name: str):
    async with AsyncSessionLocal() as db:
        # 1. 최근 5분 내 scheduled 세션 생성 여부 확인
        result = await db.execute(text("""
            SELECT id FROM sessions
            WHERE patient_id = CAST(:patient_id AS uuid)
            AND call_type = 'scheduled'
            AND started_at >= NOW() - INTERVAL '10 minutes'
        """), {"patient_id": patient_id})

        session_row = result.fetchone()

        if session_row:
            # 수신 → status 업데이트
            await db.execute(text("""
                UPDATE scheduled_calls
                SET status = 'answered'
                WHERE id = CAST(:id AS uuid)
            """), {"id": scheduled_call_id})
            await db.commit()
            print(f"통화 수신 확인: patient_id={patient_id}")
            return

        # 2. 미수신 → missed_count 증가
        result = await db.execute(text("""
            UPDATE scheduled_calls
            SET missed_count = missed_count + 1
            WHERE id = CAST(:id AS uuid)
            RETURNING missed_count
        """), {"id": scheduled_call_id})

        row = result.fetchone()
        missed_count = row[0]
        await db.commit()

        print(f"미수신 확인: patient_id={patient_id}, missed_count={missed_count}")

        if missed_count >= 3:
            # 3회 미수신 → 보호자에게 알림
            await db.execute(text("""
                UPDATE scheduled_calls
                SET status = 'missed'
                WHERE id = CAST(:id AS uuid)
            """), {"id": scheduled_call_id})

            await db.execute(text("""
                INSERT INTO missed_call_notifications (patient_id, guardian_id, scheduled_at)
                SELECT 
                    CAST(:patient_id AS uuid),
                    pg.guardian_id,
                    (SELECT scheduled_at FROM scheduled_calls WHERE id = CAST(:scheduled_call_id AS uuid))
                FROM patient_guardians pg
                WHERE pg.patient_id = CAST(:patient_id AS uuid)
            """), {"patient_id": patient_id, "scheduled_call_id": scheduled_call_id})
            
            await db.commit()

            try:
                send_missed_call_notification(guardian_fcm_token, patient_name)
                print(f"보호자 알림 발송: patient_id={patient_id}")
            except Exception as e:
                print(f"보호자 알림 발송 실패: {e}")
        else:
            # 5분 후 재발신
            retry_time = datetime.now() + timedelta(seconds=1)
            scheduler.add_job(
                lambda: send_call_notification(fcm_token, call_type="scheduled"),
                DateTrigger(run_date=retry_time),
            )
            print(f"재발신 예약: patient_id={patient_id}")

            # 재발신 후 5분 후 체크 (현재 기준 10분 후)
            scheduler.add_job(
                check_missed_call,
                DateTrigger(run_date=retry_time + timedelta(seconds=1)),
                args=[scheduled_call_id, patient_id, fcm_token, guardian_fcm_token, patient_name],
            )


async def fire_scheduled_calls():
    print("스케줄러 실행됨")
    now = datetime.now()
    current_time = now.strftime("%H:%M:00")
    current_dow = now.weekday()

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT 
                s.id,
                s.patient_id,
                p.fcm_token,
                u.name,
                g.fcm_token as guardian_fcm_token
            FROM schedules s
            JOIN patients p ON s.patient_id = p.id
            JOIN users u ON p.user_id = u.id
            JOIN patient_guardians pg ON pg.patient_id = p.id
            JOIN guardians g ON pg.guardian_id = g.id
            WHERE s.is_active = TRUE
            AND p.ai_call_enabled = TRUE
            AND s.scheduled_time = :current_time
            AND :current_dow = ANY(s.days_of_week)
            AND p.fcm_token IS NOT NULL
            AND g.fcm_token IS NOT NULL
        """), {
            "current_time": current_time,
            "current_dow": current_dow,
        })

        rows = result.fetchall()

        for row in rows:
            schedule_id = str(row[0])
            patient_id = str(row[1])
            fcm_token = row[2]
            patient_name = row[3]
            guardian_fcm_token = row[4]

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
                send_call_notification(fcm_token, call_type="requested")
                print(f"FCM 발신 완료: patient_id={patient_id}")
            except Exception as e:
                print(f"FCM 발신 실패: {e}")

            # 5분 후 미수신 확인 job 등록
            check_time = datetime.now() + timedelta(seconds=1)
            scheduler.add_job(
                check_missed_call,
                DateTrigger(run_date=check_time),
                args=[scheduled_call_id, patient_id, fcm_token, guardian_fcm_token, patient_name],
            )
            print(f"5분 후 미수신 확인 job 등록: {check_time}")


def start_scheduler():
    scheduler.add_job(
        fire_scheduled_calls,
        CronTrigger(minute="*"),
    )
    scheduler.start()