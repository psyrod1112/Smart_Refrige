"""
PC 테스트 서버 — 라즈베리파이 없이 동작
picamera2 / RPi.GPIO 미사용
OCR 성공은 POST /test/trigger_ocr 으로 수동 시뮬레이션

실행:
  pip install flask pyserial
  python test_server.py

Flutter IP 설정: api_service.dart 의 _baseUrl 을
  http://<이 PC의 로컬 IP>:5000  으로 변경
  (ipconfig 로 확인, 예: 192.168.0.10)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import serial
import threading
import time
import db
import fifo

app = Flask(__name__)
CORS(app)   # Flutter 크로스 오리진 요청 허용

# ── 설정 ───────────────────────────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE   = 9600

# ── 공유 상태 ──────────────────────────────────────────────────
_ser            = None
_lock           = threading.Lock()
_current_expiry = None   # POST /test/trigger_ocr 으로 설정
_last_temp      = None
_last_hum       = None
_last_closed_weight = None
WEIGHT_CHANGE_THRESHOLD = 30.0

# ── Serial 전송 ────────────────────────────────────────────────
def send(cmd: str):
    with _lock:
        if _ser and _ser.is_open:
            _ser.write((cmd + "\n").encode())

# ── 온도 → 보관 구역 ───────────────────────────────────────────
def storage_from_temp(temp: float) -> str:
    if temp == -99: return "냉장"
    if temp < -5:   return "냉동"
    if temp < 12:   return "냉장"
    return "상온"

# ── Serial 수신 루프 ───────────────────────────────────────────
def handle_close_weight(weight: float):
    global _last_closed_weight

    if _last_closed_weight is None:
        _last_closed_weight = weight
        print(f"[Weight] 기준 닫힘 무게 저장: {weight:.1f}g")
        return

    delta = weight - _last_closed_weight
    _last_closed_weight = weight

    if abs(delta) < WEIGHT_CHANGE_THRESHOLD:
        print(f"[Weight] 변화 없음: {weight:.1f}g ({delta:+.1f}g)")
    elif delta < 0:
        print(f"[출고 의심] 냉장고 무게 {-delta:.1f}g 감소")
    else:
        print(f"[입고/증가 감지] 냉장고 무게 {delta:.1f}g 증가")

def _read_loop():
    global _current_expiry, _last_temp, _last_hum
    while True:
        try:
            line = _ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            if line.startswith("DOOR:"):
                pass

            elif line.startswith("CLOSE_WEIGHT:"):
                handle_close_weight(float(line.split(":")[1]))

            elif line.startswith("SWITCH:"):
                parts  = line[len("SWITCH:"):].split(",")
                weight = float(parts[0])
                temp   = float(parts[1].split(":")[1])
                hum    = float(parts[2].split(":")[1])

                expiry = _current_expiry
                if expiry is None:
                    print("[Switch] OCR 결과 없음 — /test/trigger_ocr 먼저 호출하세요")
                    continue

                food_type = db.get_food_type_by_weight(weight)
                storage   = storage_from_temp(temp)
                slot      = fifo.calc_slot(expiry)

                item_id = db.insert_food_item(
                    food_type_id   = food_type["id"],
                    food_type_name = food_type["name"],
                    expired_date   = expiry,
                    weight         = weight,
                    storage        = storage,
                    slot_number    = slot
                )
                print(f"[입고 완료] id={item_id} | {food_type['name']} | "
                      f"{storage} | 유통기한={expiry.date()} | 슬롯={slot}")
                send(f"OLED:Slot {slot}")
                _current_expiry = None

            elif line.startswith("TEMP:"):
                parts      = line.split(",")
                _last_temp = float(parts[0].split(":")[1])
                _last_hum  = float(parts[1].split(":")[1])

        except Exception as e:
            print(f"[Serial 오류] {e}")
            time.sleep(0.1)

# ── 테스트 전용 API ────────────────────────────────────────────
@app.route("/test/trigger_ocr", methods=["POST"])
def trigger_ocr():
    """OCR 성공 시뮬레이션. Body: {"expired_date": "2025-12-31"}"""
    global _current_expiry
    date_str = request.json.get("expired_date", "2025-12-31")
    _current_expiry = datetime.strptime(date_str, "%Y-%m-%d")
    send("LED_R:0")
    send("STATE:WEIGHT_READY")
    return jsonify({"ok": True, "expired_date": date_str})

@app.route("/test/mock_switch", methods=["POST"])
def mock_switch():
    """스위치 + 무게 시뮬레이션 (하드웨어 없이 전체 흐름 테스트)
    Body (선택): {"weight": 200.0, "temp": 5.0, "hum": 65.0}
    trigger_ocr 먼저 호출한 후 이걸 호출해야 함
    """
    global _current_expiry
    expiry = _current_expiry
    if expiry is None:
        return jsonify({"error": "/test/trigger_ocr 먼저 호출하세요"}), 400

    data   = request.json or {}
    weight = float(data.get("weight", 200.0))
    temp   = float(data.get("temp",   5.0))

    food_type = db.get_food_type_by_weight(weight)
    storage   = storage_from_temp(temp)
    slot      = fifo.calc_slot(expiry)

    item_id = db.insert_food_item(
        food_type_id   = food_type["id"],
        food_type_name = food_type["name"],
        expired_date   = expiry,
        weight         = weight,
        storage        = storage,
        slot_number    = slot
    )
    _current_expiry = None
    send(f"OLED:Slot {slot}")
    return jsonify({"id": item_id, "slot": slot, "food_type": food_type["name"],
                    "storage": storage, "expired_date": str(expiry.date())})

# ── 기존 Flask API ─────────────────────────────────────────────
@app.route("/foods", methods=["GET"])
def get_foods():
    return jsonify(db.get_all_stored())

@app.route("/foods", methods=["POST"])
def add_food_manual():
    data = request.json
    try:
        expiry = datetime.strptime(data["expired_date"], "%Y-%m-%d")
        slot   = fifo.calc_slot(expiry)
        item_id = db.insert_food_item(
            food_type_id   = data.get("food_type_id"),
            food_type_name = data.get("food_type_name", "수동입고"),
            expired_date   = expiry,
            weight         = float(data.get("weight", 0)),
            storage        = data.get("storage", "냉장"),
            slot_number    = slot,
            image_id       = "NONE"
        )
        return jsonify({"id": item_id, "slot": slot}), 201
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

@app.route("/foods/<int:item_id>", methods=["PUT"])
def update_food(item_id):
    status_map = {"소비": "consumed", "폐기": "discarded", "이동": "moved"}
    raw    = request.json.get("status", "consumed")
    status = status_map.get(raw, raw)
    db.update_status(item_id, status)
    return jsonify({"ok": True})

@app.route("/food_types", methods=["GET"])
def get_food_types():
    return jsonify(db.get_all_food_types())

@app.route("/food_types/<int:type_id>", methods=["PUT"])
def update_food_type(type_id):
    name = request.json.get("name", "")
    if not name:
        return jsonify({"error": "name required"}), 400
    db.update_food_type_name(type_id, name)
    return jsonify({"ok": True})

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify(db.get_dashboard(_last_temp, _last_hum))

# ── 서버 시작 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import signal, atexit

    def cleanup():
        if _ser and _ser.is_open:
            _ser.close()
            print("[Serial] 포트 해제 완료")

    atexit.register(cleanup)

    def on_signal(sig, frame):
        cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGINT,  on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    db.init_db()

    try:
        _ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[Serial] 연결됨: {SERIAL_PORT}")
    except Exception as e:
        print(f"[Serial] 연결 실패: {e}  → Serial 없이 API만 동작")

    if _ser:
        threading.Thread(target=_read_loop, daemon=True).start()

    print("\n[Server] http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
