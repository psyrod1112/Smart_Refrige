import subprocess
import time
import threading
from ocr import run_ocr, parse_expiry
import serial_handler

SCAN_TIMEOUT  = 30
CAPTURE_PATH  = "/tmp/scan.jpg"

current_expiry = None
scan_active    = False
_lock = threading.Lock()

def init():
    print("[Camera] 초기화 완료 (rpicam-still 사용)")

def start_scan():
    global scan_active, current_expiry

    with _lock:
        if scan_active:
            print("[Camera] 이미 스캔 중")
            return
        scan_active    = True
        current_expiry = None

    print("[Camera] 스캔 시작 (최대 30초)")
    start = time.time()

    while scan_active:
        if time.time() - start > SCAN_TIMEOUT:
            print("[Camera] 타임아웃")
            serial_handler.send("LED_R:0")
            serial_handler.send("OLED:Timeout")
            scan_active = False
            break

        result = subprocess.run(
            ["rpicam-still", "-o", CAPTURE_PATH, "--timeout", "500", "--nopreview"],
            capture_output=True
        )

        if result.returncode != 0:
            print(f"[Camera] 촬영 실패: {result.stderr.decode()}")
            time.sleep(1)
            continue

        text = run_ocr(CAPTURE_PATH)
        print(f"[OCR] 인식 텍스트: {repr(text)}")

        date = parse_expiry(text)

        if date is None:
            print("[Camera] 인식 실패 → 재시도")
            serial_handler.send("SCAN_FAIL")
            time.sleep(1)
            continue

        print(f"[Camera] 유통기한 인식 성공: {date.date()}")
        current_expiry = date
        scan_active    = False
        serial_handler.send("LED_R:0")
        serial_handler.send("STATE:WEIGHT_READY")
        break

def close():
    pass
