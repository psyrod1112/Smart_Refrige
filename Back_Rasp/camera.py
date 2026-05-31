import subprocess
import time
import threading
from ocr import run_ocr, parse_expiry
import serial_handler

SCAN_TIMEOUT  = 300
CAPTURE_PATH  = "/tmp/scan.jpg"

current_expiry = None
scan_active    = False
_lock = threading.Lock()

def init():
    print("[Camera] Initialized (rpicam-still)")
    threading.Thread(target=start_scan, daemon=True).start()

def start_scan():
    global scan_active, current_expiry

    with _lock:
        if scan_active:
            print("[Camera] Already scanning")
            return
        if current_expiry is not None:
            print("[Camera] Expiry already set, waiting for weight")
            return
        scan_active    = True
        current_expiry = None

    print("[Camera] Scan started (timeout: 300s)")
    start = time.time()

    while scan_active:
        if time.time() - start > SCAN_TIMEOUT:
            print("[Camera] Timeout")
            serial_handler.send("LED_R:0")
            serial_handler.send("OLED:Timeout")
            scan_active = False
            break

        result = subprocess.run(
            ["rpicam-still", "-o", CAPTURE_PATH, "--timeout", "500", "--nopreview"],
            capture_output=True
        )

        if result.returncode != 0:
            print(f"[Camera] Capture failed: {result.stderr.decode()}")
            time.sleep(1)
            continue

        text = run_ocr(CAPTURE_PATH)
        print(f"[OCR] Recognized text: {repr(text)}")

        date = parse_expiry(text)

        if date is None:
            print("[Camera] Parse failed, retrying")
            serial_handler.send("SCAN_FAIL")
            time.sleep(1)
            continue

        print(f"[Camera] Expiry date found: {date.date()}")
        current_expiry = date
        scan_active    = False
        serial_handler.send("LED_R:0")
        serial_handler.send("STATE:WEIGHT_READY")
        break

def close():
    pass
