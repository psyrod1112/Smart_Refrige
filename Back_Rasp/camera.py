import time
import threading
from picamera2 import Picamera2
from ocr import run_ocr, parse_expiry
import serial_handler

SCAN_TIMEOUT  = 30          # 최대 스캔 시간 (초)
CAPTURE_PATH  = "/tmp/scan.jpg"

# 다른 모듈에서 읽어가는 공유 상태
current_expiry = None       # OCR 성공 시 datetime 저장
scan_active    = False

_cam  = None
_lock = threading.Lock()

# ── 초기화 ────────────────────────────────────────────────────
def init():
    global _cam
    _cam = Picamera2()
    cfg  = _cam.create_still_configuration(main={"size": (1280, 720)})
    _cam.configure(cfg)
    _cam.start()
    time.sleep(1)   # 워밍업
    print("[Camera] 초기화 완료")

# ── GPIO 버튼 → 이 함수 호출 ─────────────────────────────────
def start_scan():
    """스캔 시작. gpio_handler가 별도 스레드에서 호출."""
    global scan_active, current_expiry

    with _lock:
        if scan_active:
            print("[Camera] 이미 스캔 중")
            return
        scan_active    = True
        current_expiry = None

    serial_handler.send("LED_R:1")   # ④ 빨간 LED ON
    print("[Camera] 스캔 시작 (최대 30초)")

    start = time.time()

    while scan_active:
        # ── 타임아웃 체크 ────────────────────────────────────
        if time.time() - start > SCAN_TIMEOUT:
            print("[Camera] 타임아웃")
            serial_handler.send("LED_R:0")
            serial_handler.send("OLED:Timeout")
            scan_active = False
            break

        # ── 촬영 ─────────────────────────────────────────────
        _cam.capture_file(CAPTURE_PATH)

        # ── Roboflow OCR ──────────────────────────────────────
        text = run_ocr(CAPTURE_PATH)
        print(f"[OCR] 인식 텍스트: {repr(text)}")

        date = parse_expiry(text)

        # ── 실패 ─────────────────────────────────────────────
        if date is None:
            print("[Camera] 인식 실패 → 재시도")
            serial_handler.send("SCAN_FAIL")     # OLED "Scan Failed"
            time.sleep(1)
            continue

        # ── 성공 ─────────────────────────────────────────────
        print(f"[Camera] 유통기한 인식 성공: {date.date()}")
        current_expiry = date
        scan_active    = False
        serial_handler.send("LED_R:0")               # 빨간 LED OFF
        serial_handler.send("STATE:WEIGHT_READY")    # Arduino 무게 대기 모드
        break

def close():
    if _cam:
        _cam.stop()
