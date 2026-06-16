"""
유통기한 OCR 모듈 — Roboflow Cloud OCR API 기반 (로컬 모델 설치 불필요)
지원 날짜 형식: YYYY.MM.DD / YYYY-MM-DD / YY.MM.DD / YYYY년MM월DD일
"""
import re
import base64
import calendar
import cv2
import numpy as np
import requests
from datetime import datetime

ROBOFLOW_API_KEY = "9FLfxK3lx9uuy7EzGd5X"
ROBOFLOW_OCR_URL = "https://serverless.roboflow.com/-rtntv/workflows/easyocr-demo-2"


def _preprocess(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    sharpen = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(gray, -1, sharpen)


def _to_b64(img) -> str:
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _call_roboflow(img) -> str:
    try:
        resp = requests.post(
            ROBOFLOW_OCR_URL,
            headers={"Content-Type": "application/json"},
            json={"api_key": ROBOFLOW_API_KEY,
                  "inputs": {"image": {"type": "base64", "value": _to_b64(img)}}},
            timeout=15,
        )
        outputs = resp.json().get("outputs", [])
        return outputs[0].get("recognized_text", "") if outputs else ""
    except Exception as e:
        print(f"[Camera] Roboflow error: {e}")
        return ""


def _parse_date(text: str) -> str | None:
    sep = r"[.\-/,]\s*"
    patterns = [
        (r"(\d{4})" + sep + r"(\d{1,2})" + sep + r"(\d{1,2})(?:\s+\d{1,2}:\d{2})?", True),
        (r"(\d{2})"  + sep + r"(\d{1,2})" + sep + r"(\d{1,2})(?:\s+\d{1,2}:\d{2})?", True),
        (r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", True),
        (r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)",  True),
        (r"(\d{4})" + sep + r"(\d{1,2})(?!" + sep + r")", False),
        (r"(\d{2})"  + sep + r"(\d{1,2})(?!" + sep + r")", False),
    ]
    for pattern, has_day in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if has_day else None
        if y < 100:
            y += 2000
        if not (2000 <= y <= 2040 and 1 <= mo <= 12):
            continue
        if d is None:
            d = calendar.monthrange(y, mo)[1]
        if not (1 <= d <= 31):
            continue
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            continue

    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        y = int(m.group(1))
        nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", text)]
        for mo in (n for n in nums if 1 <= n <= 12):
            for d in (n for n in nums if 1 <= n <= 31 and n != mo):
                try:
                    return datetime(y, mo, d).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


def scan_from_frame(frame) -> str | None:
    """프레임 이미지에서 유통기한 날짜 문자열 추출. 실패 시 None."""
    for img in (frame, _preprocess(frame)):
        text = _call_roboflow(img)
        print(f"[Camera] INFO: {text}")
        date = _parse_date(text)
        if date:
            print(f"[Camera] SUCCESS: {date}")
            return date
    return None


def scan_expiry_date(camera_index: int = 0) -> str | None:
    """카메라로 촬영 후 유통기한 날짜 문자열 반환. 실패 시 None."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("[Camera] ERROR: Cannot open camera.")
        return None

    for _ in range(5):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[Camera] ERROR: Failed to capture frame.")
        return None

    result = scan_from_frame(frame)
    if not result:
        print("[Camera] WARN: No valid date found.")
    return result
