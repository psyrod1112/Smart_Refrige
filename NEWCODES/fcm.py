"""
Firebase Cloud Messaging (FCM HTTP v1 API) 푸시 알림 모듈
환경 변수:
  FCM_PROJECT_ID       - Firebase 프로젝트 ID (필수)
  FCM_SERVICE_ACCOUNT  - 서비스 계정 JSON 파일 경로 (기본값: firebase_service_account.json)
"""
import os

import requests

FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "")
SERVICE_ACCOUNT_FILE = os.getenv("FCM_SERVICE_ACCOUNT", "firebase_service_account.json")

_cached_token: str | None = None


def _get_access_token() -> str | None:
    global _cached_token
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as ga_requests

        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        creds.refresh(ga_requests.Request())
        _cached_token = creds.token
        return _cached_token
    except FileNotFoundError:
        print(f"[FCM] Service account file not found: {SERVICE_ACCOUNT_FILE}")
    except Exception as e:
        print(f"[FCM] Failed to get access token: {e}")
    return None


def send_push(title: str, body: str, tokens: list[str]) -> int:
    """FCM 푸시 알림을 tokens 목록에 전송. 성공한 건수를 반환."""
    if not FCM_PROJECT_ID:
        print("[FCM] FCM_PROJECT_ID not set — skipping notification")
        return 0
    if not tokens:
        print("[FCM] No registered device tokens — skipping notification")
        return 0

    access_token = _get_access_token()
    if not access_token:
        return 0

    url = f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    success = 0
    for token in tokens:
        payload = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
            }
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=5)
            if resp.status_code == 200:
                success += 1
            else:
                print(f"[FCM] Send failed ({resp.status_code}): {resp.text[:120]}")
        except requests.RequestException as e:
            print(f"[FCM] Request error: {e}")

    print(f"[FCM] {success}/{len(tokens)} sent successfully")
    return success
