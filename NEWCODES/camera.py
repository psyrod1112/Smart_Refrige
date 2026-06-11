"""
유통기한 OCR 모듈 — EasyOCR (딥러닝) 기반
지원 날짜 형식: YYYY.MM.DD / YYYY-MM-DD / YY.MM.DD / YYYY년MM월DD일
"""
import re
from datetime import datetime

import cv2
import easyocr

_DATE_PATTERNS = [
    # YYYY.MM.DD  YYYY-MM-DD  YYYY/MM/DD
    r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})",
    # YYYY년 MM월 DD일
    r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    # YY.MM.DD
    r"(\d{2})[.\-/](\d{2})[.\-/](\d{2})",
]

# 모델을 매 호출마다 로드하면 느리므로 모듈 수준에서 1회만 초기화
# 첫 실행 시 모델 다운로드 (한국어 + 영어, 수백 MB)
print("[Camera] EasyOCR model loading... (최초 실행 시 다운로드 발생)")
_reader = easyocr.Reader(["ko", "en"], gpu=False)
print("[Camera] model load complete")


def _preprocess(frame):
    """대비 강화 + 샤프닝으로 각인/레이저 인쇄 날짜 인식률 향상"""
    import numpy as np
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # CLAHE: 국소 대비 향상 (포장지 배경 불균일 대응)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # 샤프닝 커널
    sharpen = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, sharpen)
    return gray


def _parse_date(text: str) -> str | None:
    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        try:
            dt = datetime(int(y), int(mo), int(d))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def scan_from_frame(frame) -> str | None:
    """프레임 이미지에서 유통기한 날짜 문자열 추출. 실패 시 None."""
    for img in (frame, _preprocess(frame)):
        results = _reader.readtext(img)
        texts = [text for (_, text, conf) in results if conf >= 0.3]
        combined = " ".join(texts)
        print(f"[Camera] INFO: {combined}")

        date = _parse_date(combined)
        if date:
            print(f"[Camera] SUCCESS: {date}")
            return date
    return None


def scan_expiry_date(camera_index: int = 0) -> str | None:
    """
    카메라로 촬영 후 유통기한 날짜 문자열 반환. 실패 시 None.
    EasyOCR이 신뢰도 0.3 이상인 텍스트만 날짜 파싱에 사용.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("[Camera] ERROR: Cannot open camera.")
        return None

    # 자동 노출/화이트밸런스 안정화
    for _ in range(5):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[Camera] ERROR: Failed to capture frame.")
        return None

    # 원본 + 전처리 이미지 둘 다 시도
    for img in (frame, _preprocess(frame)):
        results = _reader.readtext(img)

        # results = [(bbox, text, confidence), ...]
        # 신뢰도 낮은 결과 제거 후 전체 텍스트 합치기
        texts = [text for (_, text, conf) in results if conf >= 0.3]
        combined = " ".join(texts)
        print(f"[Camera] INFO: {combined}")

        date = _parse_date(combined)
        if date:
            print(f"[Camera] SUCCESS: {date}")
            return date

    print("[Camera] WARN: No valid date found.")
    return None
