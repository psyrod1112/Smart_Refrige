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
        print(f"[OCR] Full response: {data}")

        outputs = data.get("outputs", [])
        if not outputs:
            return ""
        return outputs[0].get("recognized_text", "")

    except Exception as e:
        print(f"[OCR] Error: {e}")
        return ""

def parse_expiry(text: str) -> datetime | None:
    # sep allows optional spaces after separator (e.g. "2026. 7. 21")
    sep = r'[.\-/,]\s*'

    patterns = [
        # YYYY.MM.DD with optional spaces/time
        (r'(\d{4})' + sep + r'(\d{1,2})' + sep + r'(\d{1,2})(?:\s+\d{1,2}:\d{2})?', True),
        # YY.MM.DD
        (r'(\d{2})' + sep + r'(\d{1,2})' + sep + r'(\d{1,2})(?:\s+\d{1,2}:\d{2})?', True),
        # YYYYMMDD
        (r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)', True),
        # YYMMDD
        (r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', True),
        # YYYY.MM (no day)
        (r'(\d{4})' + sep + r'(\d{1,2})(?!' + sep + r')', False),
        # YY.MM (no day)
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
        if not (2000 <= y <= 2040 and 1 <= mo <= 12):
            continue
        if d is None:
            d = calendar.monthrange(y, mo)[1]
        if not (1 <= d <= 31):
            continue
        try:
            return datetime(y, mo, d)
        except ValueError:
            continue

    # Fallback: OCR scrambled the order — find 4-digit year then guess month/day
    m = re.search(r'\b(20\d{2})\b', text)
    if m:
        y = int(m.group(1))
        if 2000 <= y <= 2040:
            nums = [int(n) for n in re.findall(r'\b(\d{1,2})\b', text)]
            months = [n for n in nums if 1 <= n <= 12]
            days   = [n for n in nums if 1 <= n <= 31]
            for mo in months:
                for d in days:
                    if d == mo:
                        continue
                    try:
                        return datetime(y, mo, d)
                    except ValueError:
                        continue

    return None
