from datetime import datetime, date
import threading
import time

from flask import Flask, jsonify, request

import NEWCODES.camera as camera
import db
import NEWCODES.fcm as fcm
import fifo
import serial_handler

try:
    import gpio_handler
except Exception as e:
    gpio_handler = None
    _gpio_import_error = e
else:
    _gpio_import_error = None

app = Flask(__name__)

_last_temp = None
_last_hum = None
_last_closed_weight = None
_last_expiry_alert_date = None


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


@app.before_request
def _log_req():
    if request.method in ("POST", "PUT") and request.is_json:
        print(f"[{_ts()}][HTTP] {request.method} {request.path} body={request.get_json(silent=True)}")
    else:
        print(f"[{_ts()}][HTTP] {request.method} {request.path}")


@app.after_request
def _log_resp(resp):
    print(f"[{_ts()}][HTTP] -> {resp.status_code} {request.path}")
    return resp

WEIGHT_CHANGE_THRESHOLD = 30.0
EXPIRY_ALERT_INTERVAL_SEC = 60 * 60


def _storage_from_temp(temp: float) -> str:
    if temp == -99:
        return "냉장"
    if temp < -5:
        return "냉동"
    if temp < 12:
        return "냉장"
    return "상온"


def _send_push(title: str, body: str):
    threading.Thread(target=fcm.send_push, args=(title, body), daemon=True).start()


def _save_incoming(expiry: datetime, weight: float, temp: float, image_id: str = "NONE"):
    food_type = db.get_food_type_by_weight(weight)
    storage = _storage_from_temp(temp)
    slot = fifo.calc_slot(expiry)
    item_id = db.insert_food_item(
        food_type_id=food_type["id"],
        food_type_name=food_type["name"],
        expired_date=expiry,
        weight=weight,
        storage=storage,
        slot_number=slot,
        image_id=image_id,
        quantity=1,
    )
    return {
        "id": item_id,
        "slot": slot,
        "food_type": food_type["name"],
        "storage": storage,
        "expired_date": expiry.strftime("%Y-%m-%d"),
        "weight": weight,
    }


def on_door_change(is_open: bool):
    state = "open" if is_open else "closed"
    print(f"[Door] {state}")


def on_switch(weight: float, temp: float, hum: float):
    global _last_temp, _last_hum
    _last_temp, _last_hum = temp, hum

    expiry = camera.current_expiry
    if expiry is None:
        print("[Switch] Ignored: no OCR expiry is waiting")
        serial_handler.send("OLED:Scan first")
        return

    saved = _save_incoming(expiry, weight, temp)
    camera.clear_expiry()
    serial_handler.send(f"OLED:Slot {saved['slot']}")
    serial_handler.send("BUZZER")
    print(
        "[Switch] Saved incoming "
        f"id={saved['id']} type={saved['food_type']} "
        f"expiry={saved['expired_date']} weight={weight:.1f}g slot={saved['slot']}"
    )
    _send_push(
        "Incoming Complete",
        f"{saved['food_type']} stored in slot {saved['slot']}.",
    )


def on_temp_hum(temp: float, hum: float):
    global _last_temp, _last_hum
    _last_temp, _last_hum = temp, hum


def on_close_weight(weight: float):
    global _last_closed_weight

    if _last_closed_weight is None:
        _last_closed_weight = weight
        print(f"[Weight] Base weight saved: {weight:.1f}g")
        return

    delta = weight - _last_closed_weight
    _last_closed_weight = weight

    if abs(delta) < WEIGHT_CHANGE_THRESHOLD:
        print(f"[Weight] No significant change: delta={delta:+.1f}g")
        return

    if delta < 0:
        item = db.mark_next_outgoing("consumed")
        if item is None:
            print(f"[Weight] Outgoing detected ({-delta:.1f}g), but no stored item exists")
            _send_push("Outgoing Detected", f"Weight decreased by {-delta:.0f}g but no stored items found.")
            return

        print(
            "[Weight] Auto outgoing "
            f"id={item['id']} type={item.get('food_type_name', '')} delta={delta:+.1f}g"
        )
        _send_push(
            "Outgoing Detected",
            f"{item.get('food_type_name', 'item')} has been marked as outgoing.",
        )
    else:
        print(f"[Weight] Incoming-like increase detected: +{delta:.1f}g")
        _send_push(
            "Weight Increase Detected",
            "New item detected. Please scan with OCR to complete registration.",
        )


@app.route("/foods", methods=["GET"])
def get_foods():
    return jsonify(db.get_all_stored())


@app.route("/foods", methods=["POST"])
def add_food_manual():
    data = request.json or {}
    try:
        expiry = datetime.strptime(data["expired_date"], "%Y-%m-%d")
        weight = float(data.get("weight", 0))
        quantity = max(1, int(data.get("quantity", 1)))
        storage = data.get("storage", "냉장")
        food_type_id = data.get("food_type_id")
        food_type_name = data.get("food_type_name", "수동입고")
        slot = fifo.calc_slot(expiry)

        item_id = db.insert_food_item(
            food_type_id=food_type_id,
            food_type_name=food_type_name,
            expired_date=expiry,
            weight=weight,
            storage=storage,
            slot_number=slot,
            image_id="NONE",
            quantity=quantity,
        )
        _send_push("Manual Incoming Complete", f"{food_type_name} stored in slot {slot}.")
        return jsonify({"id": item_id, "slot": slot}), 201
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/foods/<int:item_id>", methods=["PUT"])
def update_food(item_id):
    data = request.json or {}
    status = data.get("status", "consumed")
    db.update_status(item_id, status)
    _send_push("Outgoing Complete", f"Item #{item_id} status changed to {status}.")
    return jsonify({"ok": True})


@app.route("/food_types", methods=["GET"])
def get_food_types():
    return jsonify(db.get_all_food_types())


@app.route("/food_types/<int:type_id>", methods=["PUT"])
def update_food_type(type_id):
    name = (request.json or {}).get("name", "")
    if not name:
        return jsonify({"error": "name required"}), 400
    db.update_food_type_name(type_id, name)
    return jsonify({"ok": True})


@app.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify(db.get_dashboard(_last_temp, _last_hum))


@app.route("/scan/start", methods=["POST"])
def start_scan():
    threading.Thread(target=camera.start_scan, daemon=True).start()
    return jsonify({"ok": True})


def _expiry_alert_loop():
    global _last_expiry_alert_date
    while True:
        try:
            today = date.today()
            if _last_expiry_alert_date != today:
                count = db.get_dashboard(_last_temp, _last_hum)["expiring_soon"]
                if count > 0:
                    _send_push("Expiry Alert", f"{count} item(s) expiring within 3 days.")
                _last_expiry_alert_date = today
        except Exception as e:
            print(f"[ExpiryAlert] Failed: {e}")
        time.sleep(EXPIRY_ALERT_INTERVAL_SEC)


if __name__ == "__main__":
    db.init_db()
    threading.Thread(target=_expiry_alert_loop, daemon=True).start()

    try:
        camera.init()
    except Exception as e:
        print(f"[Camera] Init failed: {e}. Running without camera.")

    try:
        serial_handler.init(on_door_change, on_switch, on_temp_hum, on_close_weight)
        serial_handler.send("LED_R:1")
    except Exception as e:
        print(f"[Serial] Init failed: {e}. Running without serial.")

    try:
        if gpio_handler is None:
            raise RuntimeError(_gpio_import_error)
        gpio_handler.init(on_button_press=camera.start_scan)
    except Exception as e:
        print(f"[GPIO] Init failed: {e}. Running without GPIO.")

    print("[Server] Flask started -- http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
