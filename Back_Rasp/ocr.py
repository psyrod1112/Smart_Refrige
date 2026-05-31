import re
import base64
import calendar
import requests
from datetime import datetime

ROBOFLOW_API_KEY = "9FLfxK3lx9uuy7EzGd5X"
ROBOFLOW_OCR_URL = "https://serverless.roboflow.com/-rtntv/workflows/easyocr-demo-2"

def run_ocr(image_path: str) -> str:
    """이미지를 Roboflow Workflow에 보내고 인식된 텍스트 반환. 실패 시 빈 문자열."""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            ROBOFLOW_OCR_URL,
            headers={"Content-Type": "application/json"},
            json={
                "api_key": ROBOFLOW_API_KEY,
                "inputs": {
                    "image": {"type": "base64", "value": b64}
                }
            },
            timeout=15
        )
        data = resp.json()
        print(f"[OCR] 응답 전체: {data}")   # 처음엔 응답 구조 확인용으로 출력

        outputs = data.get("outputs", [])
        if not outputs:
            return ""
        return outputs[0].get("recognized_text", "")

    except Exception as e:
        print(f"[OCR] 오류: {e}")
        return ""

def parse_expiry(text: str) -> datetime | None:
    """
    텍스트에서 유통기한 날짜 추출.
    지원 포맷:
      2025.12.31 / 25.12.31         (년.월.일)
      2025/12/31 / 25-12-31         (구분자 무관)
      2025.12.31 15:30              (시각 포함 → 날짜만 사용)
      2025.12 / 25.12               (일 없음 → 해당 월 말일로)
      20251231 / 251231             (구분자 없는 숫자)
    """
    sep = r'[.\-/]'

    # 우선순위 순서: 구체적인 패턴 먼저
    patterns = [
        # YYYY.MM.DD (시각 포함 허용)
        (r'(\d{4})' + sep + r'(\d{1,2})' + sep + r'(\d{1,2})(?:\s+\d{1,2}:\d{2})?', True),
        # YY.MM.DD (시각 포함 허용)
        (r'(\d{2})' + sep + r'(\d{1,2})' + sep + r'(\d{1,2})(?:\s+\d{1,2}:\d{2})?', True),
        # YYYYMMDD
        (r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)', True),
        # YYMMDD
        (r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', True),
        # YYYY.MM (일 없음)
        (r'(\d{4})' + sep + r'(\d{1,2})(?!' + sep + r')', False),
        # YY.MM (일 없음)
        (r'(\d{2})' + sep + r'(\d{1,2})(?!' + sep + r')', False),
    ]

    for pattern, has_day in patterns:
        m = re.search(pattern, text)
        if not m:
            continue

        y  = int(m.group(1))
        mo = int(m.group(2))
        d  = int(m.group(3)) if has_day else None

        if y < 100:
            y += 2000

        # 말도 안 되는 날짜 필터 (연도 범위 넉넉하게)
        if not (2000 <= y <= 2040 and 1 <= mo <= 12):
            continue

        # 일(day) 없는 포맷 → 해당 월의 마지막 날로
        if d is None:
            d = calendar.monthrange(y, mo)[1]

        if not (1 <= d <= 31):
            continue

        try:
            return datetime(y, mo, d)
        except ValueError:
            continue   # 2월 30일 같은 불가능한 날짜

    return None
