import firebase_admin
from firebase_admin import credentials, messaging
from app.config import settings

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)


def send_call_notification(fcm_token: str):
    """환자에게 스케줄된 통화 FCM 발신"""
    message = messaging.Message(
        token=fcm_token,
        data={
            "type": "AI_CALL",
            "call_type": "scheduled",
        },
        notification=messaging.Notification(
            title="AI 전화",
            body="전화가 왔습니다.",
        ),
        android=messaging.AndroidConfig(
            priority="high",
            ttl=0,
            direct_boot_ok=True,
            notification=messaging.AndroidNotification(
                channel_id="default",
                sound="default",
                sticky=True,
                default_sound=True,
                default_vibrate_timings=True
            )
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
        ),
    )
    response = messaging.send(message)
    return response


def send_missed_call_notification(fcm_token: str, patient_name: str):
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