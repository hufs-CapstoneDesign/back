import firebase_admin
from firebase_admin import credentials, messaging
from app.config import settings

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)


async def send_call_notification(fcm_token: str, patient_id: str, schedule_id: str):
    """환자에게 스케줄된 통화 FCM 발신"""
    message = messaging.Message(
        token=fcm_token,
        data={
            "type": "scheduled_call",
            "patient_id": patient_id,
            "schedule_id": schedule_id,
        },
        android=messaging.AndroidConfig(
            priority="high",  # 앱 꺼져있을 때도 즉시 전달
        ),
    )
    response = messaging.send(message)
    return response


async def send_missed_call_notification(fcm_token: str, patient_name: str):
    """보호자에게 미수신 알림 FCM 발신"""
    message = messaging.Message(
        token=fcm_token,
        notification=messaging.Notification(
            title="미수신 알림",
            body=f"{patient_name}님이 3회 연속 전화를 받지 않았습니다.",
        ),
        android=messaging.AndroidConfig(
            priority="high",
        ),
    )
    response = messaging.send(message)
    return response