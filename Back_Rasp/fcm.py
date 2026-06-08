import glob
from pathlib import Path

_initialized = False
_available = True

BASE_DIR = Path(__file__).resolve().parent
TOPIC = "all_users"

def _find_credential() -> Path:
    matches = glob.glob(str(BASE_DIR / "*firebase-adminsdk*.json"))
    if matches:
        return Path(matches[0])
    return BASE_DIR / "firebase-adminsdk.json"

CREDENTIAL_PATH = _find_credential()


def _init() -> bool:
    global _initialized, _available
    if not _available:
        return False
    if _initialized:
        return True

    if not CREDENTIAL_PATH.exists():
        print(f"[FCM] Skipped: missing {CREDENTIAL_PATH.name}")
        _available = False
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as e:
        print(f"[FCM] Skipped: firebase_admin not installed ({e})")
        _available = False
        return False

    cred = credentials.Certificate(str(CREDENTIAL_PATH))
    firebase_admin.initialize_app(cred)
    _initialized = True
    return True


def send_push(title: str, body: str):
    try:
        if not _init():
            return
        from firebase_admin import messaging

        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=TOPIC,
        )
        messaging.send(msg)
        print(f"[FCM] Sent: {title}")
    except Exception as e:
        print(f"[FCM] Failed: {e}")
