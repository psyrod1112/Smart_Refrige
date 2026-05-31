from flask import Flask, jsonify, request
import db, fifo, camera, serial_handler, gpio_handler

app = Flask(__name__)

# ── 공유 상태 ──────────────────────────────────────────────────
_last_temp = None
_last_hum  = None
_last_closed_weight = None
WEIGHT_CHANGE_THRESHOLD = 30.0

# ── 보관 구역 판단 (온도 기반) ─────────────────────────────────
def _storage_from_temp(temp: float) -> str:
    if temp == -99:
        return "냉장"        # 온습도 오류 시 기본값
    if temp < -5:
        return "냉동"
    if temp < 12:
        return "냉장"
    return "상온"

# ── Serial 콜백 ───────────────────────────────────────────────
def on_door_change(_is_open: bool):
    pass

def on_switch(weight: float, temp: float, _hum: float):
    """⑩ 핵심 로직 — 무게 + 온도 + 유통기한 → DB 저장 → FEFO → OLED"""
    expiry = camera.current_expiry
    if expiry is None:
        print("[Switch] OCR 결과 없음, 무시")
        return

    food_type = db.get_food_type_by_weight(weight)
    storage   = _storage_from_temp(temp)
    slot      = fifo.calc_slot(expiry)

    item_id = db.insert_food_item(
        food_type_id   = food_type["id"],
        food_type_name = food_type["name"],
        expired_date   = expiry,
        weight         = weight,
        storage        = storage,
        slot_number    = slot
    )

    print(f"[입고] id={item_id} | {food_type['name']} | {storage} | "
          f"유통기한={expiry.date()} | 무게={weight}g | 슬롯={slot}")

    # ⑪ Arduino OLED
    serial_handler.send(f"OLED:Slot {slot}")

    # ⑪ FCM 푸시
    try:
        from fcm import send_push
        send_push("입고 완료",
                  f"{food_type['name']} | 유통기한 {expiry.strftime('%Y.%m.%d')} | {slot}번 슬롯")
    except Exception as e:
        print(f"[FCM] 전송 실패: {e}")

    camera.current_expiry = None   # 상태 리셋

def on_temp_hum(temp: float, hum: float):
    global _last_temp, _last_hum
    _last_temp, _last_hum = temp, hum

def on_close_weight(weight: float):
    global _last_closed_weight

    if _last_closed_weight is None:
        _last_closed_weight = weight
        print(f"[Weight] 기준 닫힘 무게 저장: {weight:.1f}g")
        return

    delta = weight - _last_closed_weight
    _last_closed_weight = weight

    if abs(delta) < WEIGHT_CHANGE_THRESHOLD:
        return
    if delta < 0:
        print(f"[출고 의심] 냉장고 무게 {-delta:.1f}g 감소")
    else:
        print(f"[입고/증가 감지] 냉장고 무게 {delta:.1f}g 증가")

# ── Flask REST API ────────────────────────────────────────────
@app.route("/foods", methods=["GET"])
def get_foods():
    return jsonify(db.get_all_stored())

@app.route("/foods", methods=["POST"])
def add_food_manual():
    """수동 입고 — Flutter 앱에서 호출"""
    data = request.json
    try:
        from datetime import datetime as dt
        expiry         = dt.strptime(data["expired_date"], "%Y-%m-%d")
        weight         = float(data.get("weight", 0))
        storage        = data.get("storage", "냉장")
        food_type_id   = data.get("food_type_id")
        food_type_name = data.get("food_type_name", "수동입고")
        slot           = fifo.calc_slot(expiry)

        item_id = db.insert_food_item(
            food_type_id=food_type_id, food_type_name=food_type_name,
            expired_date=expiry, weight=weight, storage=storage,
            slot_number=slot, image_id="NONE"
        )
        return jsonify({"id": item_id, "slot": slot}), 201
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

@app.route("/foods/<int:item_id>", methods=["PUT"])
def update_food(item_id):
    """출고 처리"""
    status = request.json.get("status", "consumed")
    db.update_status(item_id, status)
    return jsonify({"ok": True})

@app.route("/food_types", methods=["GET"])
def get_food_types():
    return jsonify(db.get_all_food_types())

@app.route("/food_types/<int:type_id>", methods=["PUT"])
def update_food_type(type_id):
    """FoodType 이름 변경"""
    name = request.json.get("name", "")
    if not name:
        return jsonify({"error": "name required"}), 400
    db.update_food_type_name(type_id, name)
    return jsonify({"ok": True})

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify(db.get_dashboard(_last_temp, _last_hum))

# ── 서버 시작 ─────────────────────────────────────────────────
if __name__ == "__main__":
    db.init_db()
    camera.init()
    serial_handler.init(on_door_change, on_switch, on_temp_hum, on_close_weight)
    gpio_handler.init(on_button_press=camera.start_scan)
    print("[Server] Flask 시작 — http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
