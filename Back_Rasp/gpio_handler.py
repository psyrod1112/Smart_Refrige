import RPi.GPIO as GPIO
import threading

BUTTON_PIN = 17   # BCM 번호, 자유롭게 변경 가능

_on_button_press = None   # fn() — camera.py의 start_scan 주입

def init(on_button_press):
    global _on_button_press
    _on_button_press = on_button_press

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(
        BUTTON_PIN,
        GPIO.FALLING,
        callback=_callback,
        bouncetime=500
    )
    print(f"[GPIO] Button ready (BCM {BUTTON_PIN})")

def cleanup():
    GPIO.cleanup()

def _callback(channel):
    if _on_button_press:
        # 버튼 누름 → 별도 스레드에서 스캔 시작 (블로킹 방지)
        threading.Thread(target=_on_button_press, daemon=True).start()
