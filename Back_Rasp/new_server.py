from datetime import datetime
import threading

from flask import Flask, jsonify, request
import serial_handler

app = Flask(__name__)

# ── 상태 변수 ───────────────────────────────
_last_temp   = None
_last_hum    = None


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ── Flask 요청/응답 로그 ─────────────────────
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


# ── 시리얼 콜백 (Arduino → Pi) ──────────────
def on_door_change(is_open: bool):
    print(f"[Door] {'open' if is_open else 'closed'}")
    # TODO

def on_switch(weight: float, temp: float, hum: float):
    global _last_temp, _last_hum
    _last_temp, _last_hum = temp, hum
    print(f"[Switch] weight={weight:.1f}g temp={temp:.1f} hum={hum:.1f}")
    # TODO

def on_temp_hum(temp: float, hum: float):
    global _last_temp, _last_hum
    _last_temp, _last_hum = temp, hum
    print(f"[Temp] temp={temp:.1f} hum={hum:.1f}")

def on_close_weight(weight: float):
    print(f"[Weight] close weight={weight:.1f}g")
    # TODO


# ── REST 엔드포인트 ──────────────────────────
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True, "temp": _last_temp, "hum": _last_hum})

# TODO: 엔드포인트 추가


# ── 진입점 ──────────────────────────────────
if __name__ == "__main__":
    try:
        serial_handler.init(on_door_change, on_switch, on_temp_hum, on_close_weight)
        serial_handler.send("LED_R:1")
    except Exception as e:
        print(f"[Serial] Init failed: {e}. Running without serial.")

    print("[Server] started -- http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
