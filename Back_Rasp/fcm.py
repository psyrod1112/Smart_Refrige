import firebase_admin
from firebase_admin import credentials, messaging

_initialized = False

def _init():
    global _initialized
    if not _initialized:
        cred = credentials.Certificate("firebase-adminsdk.json")  # Firebase 콘솔에서 다운로드
        firebase_admin.initialize_app(cred)
        _initialized = True

def send_push(title: str, body: str):
    """FCM 푸시 알림 전송 (topic 방식 — 앱에서 'all_users' 구독 필요)"""
    try:
        _init()
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic="all_users"
        )
        messaging.send(msg)
        print(f"[FCM] 전송 완료: {title}")
    except Exception as e:
        print(f"[FCM] 전송 실패: {e}")
