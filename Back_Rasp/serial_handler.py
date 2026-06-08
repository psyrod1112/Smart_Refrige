import serial
import threading
import time

SERIAL_PORT = "/dev/ttyACM0"   # Pi에서 Arduino 연결 포트 (ls /dev/tty* 로 확인)
BAUD_RATE   = 9600

_ser  = None
_lock = threading.Lock()

# 외부에서 주입받는 콜백들 (rasp_server.py에서 등록)
_on_door_change = None   # fn(is_open: bool)
_on_switch      = None   # fn(weight: float, temp: float, hum: float)
_on_temp_hum    = None   # fn(temp: float, hum: float)
_on_close_weight = None  # fn(weight: float)

def init(on_door_change, on_switch, on_temp_hum, on_close_weight=None):
    """Serial 포트 열고 수신 스레드 시작"""
    global _ser, _on_door_change, _on_switch, _on_temp_hum, _on_close_weight
    _on_door_change = on_door_change
    _on_switch      = on_switch
    _on_temp_hum    = on_temp_hum
    _on_close_weight = on_close_weight

    _ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    t = threading.Thread(target=_read_loop, daemon=True)
    t.start()
    print(f"[Serial] Connected: {SERIAL_PORT}")

def send(cmd: str):
    """Arduino로 명령 전송 (줄바꿈 자동 추가)"""
    with _lock:
        if _ser and _ser.is_open:
            _ser.write((cmd + "\n").encode())
            print(f"[Serial] TX: {cmd}")

def _read_loop():
    """백그라운드에서 Arduino 메시지 수신"""
    while True:
        try:
            line = _ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            print(f"[Serial] RX: {line}")
            _parse(line)
        except Exception as e:
            print(f"[Serial] Receive error: {e}")

def _parse(line: str):
    if line.startswith("DOOR:"):
        is_open = line.split(":")[1] == "1"
        if _on_door_change:
            _on_door_change(is_open)

    elif line.startswith("SWITCH:"):
        try:
            # 형식: SWITCH:215.3,T:4.2,H:72.5
            parts  = line[len("SWITCH:"):].split(",")
            weight = float(parts[0])
            temp   = float(parts[1].split(":")[1])
            hum    = float(parts[2].split(":")[1])
            if _on_switch:
                _on_switch(weight, temp, hum)
        except (ValueError, IndexError) as e:
            print(f"[Serial] Parse error (SWITCH): {e} raw={line!r}")

    elif line.startswith("CLOSE_WEIGHT:"):
        try:
            weight = float(line.split(":")[1])
            if _on_close_weight:
                _on_close_weight(weight)
        except (ValueError, IndexError) as e:
            print(f"[Serial] Parse error (CLOSE_WEIGHT): {e} raw={line!r}")

    elif line.startswith("TEMP:"):
        try:
            # 형식: TEMP:23.5,HUM:60.2
            parts = line.split(",")
            temp = float(parts[0].split(":")[1])
            hum  = float(parts[1].split(":")[1])
            if _on_temp_hum:
                _on_temp_hum(temp, hum)
        except (ValueError, IndexError) as e:
            print(f"[Serial] Parse error (TEMP): {e} raw={line!r}")

    elif not line.startswith("["):
        print(f"[Serial] Unknown message: {line!r}")
