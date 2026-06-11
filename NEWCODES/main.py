"""
라즈베리파이 메인 서버
  - 아두이노 시리얼 수신 스레드
  - Flask REST API
  - APScheduler 유통기한 알림 (09:00, 15:00)
"""
import threading
import time
import uuid

import serial
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request

import NEWCODES.camera as camera
import NEWCODES.database as database
import NEWCODES.fcm as fcm

# ★ 포트를 환경에 맞게 수정: /dev/ttyUSB0 또는 /dev/ttyACM0 ★
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 9600
SCAN_TIMEOUT_SEC = 300

app = Flask(__name__)

try:
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
    print(f"[Serial] {SERIAL_PORT} 연결됨")
except serial.SerialException as e:
    print(f"[Serial] 연결 실패: {e}")
    ser = None

_pending: dict = {}  # 스캔 결과 임시 보관 (유통기한 등 세션 변수)
latest_temp = 0.0
latest_hum = 0.0


def _send_arduino(cmd: str):
    if ser and ser.is_open:
        ser.write((cmd + "\n").encode())
        print(f"[To Arduino] {cmd}")


# ── 노란 LED 상태 업데이트 ────────────────────────────
def update_yellow_led():
    items = database.get_expiring_foods(days=3)
    if items:
        _send_arduino("LED_Y:1")
        print("[LED] Yellow LED ON (Expiring items detected)")
    else:
        _send_arduino("LED_Y:0")
        print("[LED] Yellow LED OFF")


# ── 실시간 카메라 스캔 스레드 ──────────────────────────
def run_inbound_scan_loop():
    global _pending
    _pending["scan_active"] = True
    _pending["expiry_date"] = None
    _pending["manual_input"] = False
    _pending["weights"] = []

    print("[Scan] Real-time camera scan thread started.")

    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[Camera] Error: Cannot open camera.")
        _send_arduino("PROGRESS:0")
        _pending["scan_active"] = False
        return

    # 성능을 위해 해상도 축소
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # 카메라 오토 포커스/노출 안정화를 위해 5프레임 버림
    for _ in range(5):
        if not _pending.get("scan_active"):
            break
        cap.read()

    date_found = None
    scan_started_at = time.time()
    while _pending.get("scan_active"):
        if time.time() - scan_started_at > SCAN_TIMEOUT_SEC:
            print("[Scan] WARN: 5-minute timeout. Sending failure signal.")
            break

        # 1. 어플 수동 등록 체크
        if _pending.get("manual_input"):
            date_found = _pending.get("expiry_date")
            print(f"[Scan] SUCCESS: app input detected {date_found}")
            break

        # 2. 카메라 프레임 읽기
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        # 3. EasyOCR 인식 시도
        expiry = camera.scan_from_frame(frame)
        if expiry:
            date_found = expiry
            print(f"[Scan] SUCCESS: camera input detected {date_found}")
            break

        time.sleep(0.1)

    cap.release()
    _pending["scan_active"] = False

    # 스캔 종료 처리
    if date_found:
        _pending["expiry_date"] = date_found
        slot = database.get_slot_status()
        if slot["status"] == "FIFO":
            # 슬롯 정상 상태 — DB 기준 진열 위치 계산 후 바로 진행
            position = database.calculate_display_position(date_found)
            _send_arduino(f"PROGRESS:1,FIFO:1,POS:{position}")
            print(f"[Scan] 슬롯 FIFO, 진열 위치={position}")
        else:
            # 슬롯 CONFIRM 상태 (이전 출고 순서 위반 미처리) — 먼저 DB 수정 필요
            n = int(slot.get("confirm_delta", 0))
            tokens = database.get_all_tokens()
            fcm.send_push(
                "DB 수정 필요",
                f"미처리 출고 항목이 있습니다. ({n}개) 앱에서 확인 후 입고해주세요.",
                tokens,
            )
            _send_arduino(f"PROGRESS:1,FIFO:0,N:{n}")
            print(f"[Scan] 슬롯 CONFIRM, n={n} — DB 수정 대기")
    else:
        _send_arduino("PROGRESS:0")
        print("[Scan] WARN: Scan failed or canceled by user.")


# ── 입고 / 출고 처리 ─────────────────────────────────────
def handle_inbound(weight: float):
    global _pending
    expiry = _pending.get("expiry_date")
    if not expiry:
        print("[Inbound] ERROR: Expiry date is not set.")
        return

    food_id = database.insert_food(
        food_id=f"F{uuid.uuid4().hex[:8]}",
        name=_pending.get("food_name", "Unknown"),
        expiry_date=expiry,
        weight_gram=weight,
        quantity=int(_pending.get("quantity", 1) or 1),
    )
    _pending["last_inbound_food_id"] = food_id
    tokens = database.get_all_tokens()
    fcm.send_push(
        "New food registered",
        "Please open the app and enter the food name and expiry date.",
        tokens,
    )
    print(f"[Inbound] SUCCESS: weight={weight}g")



# ── 아두이노 시리얼 리스너 ──────────────────────────────
def arduino_listener():
    buf = ""
    # 최초 구동 시 노란 LED 상태 한번 셋팅
    time.sleep(2)
    update_yellow_led()

    while True:
        if ser and ser.in_waiting:
            try:
                buf += ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        process_line(line)
            except Exception as e:
                print(f"[Serial] 오류: {e}")
        time.sleep(0.05)


def process_line(line: str):
    global latest_temp, latest_hum, _pending
    print(f"[Arduino] {line}")

    # 1. 입고 요청
    if line == "INBOUND_REQ":
        # 현재 보관 수량 계산 (quantity의 합)
        foods = database.get_all_foods()
        current_count = sum(f["quantity"] for f in foods)
        _send_arduino("INPUT_OK")
        _send_arduino(f"START_COUNT:{current_count}")
        # 스캔 루프 스레드 실행
        threading.Thread(target=run_inbound_scan_loop, daemon=True).start()

    # 2. 입고 취소
    elif line == "INBOUND_CANCEL":
        _pending["scan_active"] = False
        _pending.clear()
        print("[Inbound] 아두이노 강제 취소 수신")

    # 3. 입고 무게 확정
    elif line.startswith("CONFIRM_WEIGHT:"):
        weight = float(line.split(":")[1])
        handle_inbound(weight)
        foods = database.get_all_foods()
        new_count = sum(f["quantity"] for f in foods)
        _send_arduino(f"COUNT:{new_count}")
        update_yellow_led()

    # 4. 입고 세션 완료
    elif line == "INBOUND_END":
        foods = database.get_all_foods()
        if foods:
            total_weight = sum(f.get("weight_gram", 0) or 0 for f in foods)
            total_qty = sum(f.get("quantity", 1) or 1 for f in foods)
            if total_qty > 0:
                database.set_slot_base_weight(1, total_weight / total_qty)
        database.resolve_slot_confirm()
        _pending.clear()
        _send_arduino("INBOUND_COMPLETE")
        print("[Inbound] 세션 종료 — 평균 무게 갱신 완료")

    # 5. 출고 요청 시작 (초기값 수신)
    # 포맷: OUTBOUND_REQ:W:{weight},D:{distance}
    elif line.startswith("OUTBOUND_REQ:"):
        try:
            parts = line.split(":")
            # parts = ["OUTBOUND_REQ", "W", "{weight},D", "{distance}"]
            # 더 안전한 파싱
            sub_parts = line.replace("OUTBOUND_REQ:", "").split(",")
            w_init = float(sub_parts[0].split("W:")[1])
            d_init = float(sub_parts[1].split("D:")[1])
            
            _pending["outbound_w_init"] = w_init
            _pending["outbound_d_init"] = d_init
            
            _send_arduino("REMOVE_ITEM")
            print(f"[Outbound] 시작 - 초기무게={w_init}g, 초기거리={d_init}cm")
        except Exception as e:
            print(f"[Outbound] 시작 데이터 파싱 에러: {e}")

    # 6. 출고 요청 종료 및 비교 분석
    # 포맷: OUTBOUND_FINAL:W:{weight},D:{distance}
    elif line.startswith("OUTBOUND_FINAL:"):
        try:
            sub_parts = line.replace("OUTBOUND_FINAL:", "").split(",")
            w_final = float(sub_parts[0].split("W:")[1])
            d_final = float(sub_parts[1].split("D:")[1])
            
            w_init = _pending.get("outbound_w_init", 0.0)
            d_init = _pending.get("outbound_d_init", 0.0)
            
            delta_w = w_init - w_final
            delta_d = abs(d_final - d_init)
            
            print(f"[Outbound] 종료 비교 - w_diff={delta_w:.1f}g, d_diff={delta_d:.1f}cm")
            
            if delta_w < 5.0:
                # 무게 변화 없음 -> 그대로 복귀
                database.resolve_slot_confirm()
                _send_arduino("OUTBOUND_FIFO_OK")
                print("[Outbound] 무게 감소량이 미미하여 취소 처리합니다.")
            else:
                # 꺼내간 개수 계산 (슬롯 고유 무게 우선, 없으면 DB 평균 사용)
                unit_weight = database.get_slot_base_weight()
                if unit_weight is None:
                    foods = database.get_all_foods()
                    if foods:
                        total_qty = sum(max(1, int(f["quantity"])) for f in foods)
                        total_weight = sum(
                            f["weight_gram"] * max(1, int(f["quantity"]))
                            for f in foods
                        )
                        unit_weight = total_weight / total_qty
                    else:
                        unit_weight = 150.0  # 기본값
                removed_qty = max(1, round(delta_w / unit_weight))
                
                # 거리 변화 검증 (5.0cm 이상 변화시 FIFO로 판별)
                if delta_d > 5.0:
                    # FIFO 만족 -> 가장 오래된(유통기한 짧은) 물건 삭제
                    deleted_ids = database.delete_oldest_foods(removed_qty)
                    database.resolve_slot_confirm()
                    _send_arduino("OUTBOUND_FIFO_OK")
                    update_yellow_led()
                    print(f"[Outbound] FIFO 성공 - {removed_qty}개 출고 완료 (ID: {deleted_ids})")
                else:
                    # CONFIRM 상태 진입 (FIFO 순서 위반 — 앞이 아닌 뒤쪽 물건 꺼냄)
                    database.mark_slot_confirm(removed_qty, "OUTBOUND")
                    tokens = database.get_all_tokens()
                    fcm.send_push(
                        "출고 순서 확인 필요",
                        f"FIFO 순서에 맞지 않는 출고가 감지됐습니다. ({removed_qty}개) 앱에서 확인해주세요.",
                        tokens,
                    )
                    _send_arduino(f"OUTBOUND_CONFIRM_ERR:{removed_qty}")
                    print(f"[Outbound] FIFO 순서 위반 (CONFIRM) - {removed_qty}개, RED LED 경고")
            
            _pending.clear()
        except Exception as e:
            print(f"[Outbound] 종료 데이터 파싱 에러: {e}")
            _send_arduino("OUTBOUND_FIFO_OK")

    # 7. 온습도 파싱
    elif line.startswith("ENV:"):
        # ENV:T:24.5,H:50.2
        try:
            parts = line.split(",")
            for part in parts:
                if part.startswith("ENV:T:"):
                    latest_temp = float(part.split("T:")[1])
                elif part.startswith("H:"):
                    latest_hum = float(part.split("H:")[1])
            print(f"[Env] Temp={latest_temp}°C, Humidity={latest_hum}%")
        except Exception as e:
            print(f"[Env] 데이터 파싱 에러: {e}")


# ── APScheduler: 유통기한 알림 ──────────────────────────
def expiry_alert_job():
    update_yellow_led()
    if database.already_notified_today("EXPIRY_ALERT"):
        return
    items = database.get_expiring_foods(days=3)
    if items:
        database.log_notification("EXPIRY_ALERT")
        print(f"[Scheduler] 유통기한 임박 {len(items)}개")


# ── Flask API ──────────────────────────────────────────
@app.route("/scan", methods=["POST"])
def api_scan():
    """외부 앱 또는 버튼에서 카메라 스캔 요청"""
    success = False
    expiry = camera.scan_expiry_date()
    if expiry:
        _pending["expiry_date"] = expiry
        success = True
    return jsonify({"success": success, "expiry_date": expiry})


@app.route("/inbound/manual", methods=["POST"])
def api_manual_inbound():
    """앱에서 수동으로 유통기한을 입력하는 엔드포인트"""
    global _pending
    data = request.json or {}
    expiry = data.get("expiry_date")
    if not expiry:
        return jsonify({"error": "Expiry date is required"}), 400

    food_name = data.get("name") or data.get("food_name") or data.get("food_type_name")
    quantity = data.get("quantity")
    food_id = data.get("food_id") or _pending.get("last_inbound_food_id")

    if food_id is not None and not _pending.get("scan_active"):
        fields = {"expiry_date": expiry}
        if food_name:
            fields["name"] = food_name
        if quantity is not None:
            fields["quantity"] = quantity
        ok = database.update_food(int(food_id), fields)
        if not ok:
            return jsonify({"error": "Food item not found or no fields updated"}), 404
        update_yellow_led()
        return jsonify({"success": True, "food_id": int(food_id)})

    _pending["expiry_date"] = expiry
    _pending["manual_input"] = True
    if food_name:
        _pending["food_name"] = food_name
    if quantity is not None:
        _pending["quantity"] = quantity
    return jsonify({"success": True})


@app.route("/inbound/app_done", methods=["POST"])
def api_inbound_app_done():
    """앱에서 DB 수정 완료 후 호출 — 갱신된 DB 기준 진열 위치 계산 후 S_2 전환"""
    expiry = _pending.get("expiry_date")
    if not expiry:
        return jsonify({"error": "No active inbound session"}), 400
    position = database.calculate_display_position(expiry)
    _send_arduino(f"INBOUND_DB_DONE:{position}")
    return jsonify({"success": True, "display_position": position})


@app.route("/app/connect", methods=["POST"])
def api_app_connect():
    """앱에서 유통기한 확인 알림 클릭 시 호출되어 아두이노 화면을 갱신하는 엔드포인트"""
    _send_arduino("APP_CONNECTED")
    return jsonify({"success": True, "slot": database.get_slot_status()})


@app.route("/fcm/token", methods=["POST"])
def api_register_fcm_token():
    data = request.json or {}
    token = data.get("token")
    if not token:
        return jsonify({"error": "token required"}), 400
    database.upsert_token(token)
    return jsonify({"success": True})


@app.route("/environment", methods=["GET"])
def api_environment():
    """온습도 상태 조회 API"""
    return jsonify({"temperature": latest_temp, "humidity": latest_hum})


@app.route("/foods", methods=["GET"])
def api_foods():
    return jsonify({
        "slot": database.get_slot_status(),
        "foods": database.get_all_foods(),
    })


@app.route("/foods", methods=["POST"])
def api_create_food():
    data = request.json or {}
    expiry = data.get("expiry_date") or data.get("expired_date")
    if not expiry:
        return jsonify({"error": "expiry_date required"}), 400

    name = data.get("name") or data.get("food_name") or data.get("food_type_name") or "Manual"
    weight = float(data.get("weight_gram", data.get("weight", 0)) or 0)
    quantity = max(1, int(data.get("quantity", 1) or 1))
    food_id = database.insert_food(
        food_id=f"F{uuid.uuid4().hex[:8]}",
        name=name,
        expiry_date=expiry,
        weight_gram=weight,
        quantity=quantity,
    )
    position = database.calculate_display_position(expiry)
    update_yellow_led()
    return jsonify({"id": food_id, "display_position": position}), 201


@app.route("/foods/<int:food_id>", methods=["PATCH"])
def api_update_food(food_id):
    fields = request.json
    ok = database.update_food(food_id, fields)
    if ok:
        update_yellow_led()
    return jsonify({"success": ok})


@app.route("/outbound/confirm", methods=["POST"])
def api_confirm_outbound():
    data = request.json
    food_id = data.get("food_id")
    delta = float(data.get("delta", 0))
    new_qty = None
    if food_id is not None:
        new_qty = database.confirm_outbound(int(food_id), delta)
        if new_qty is None:
            return jsonify({"error": "not found"}), 404
    slot = database.resolve_slot_confirm()
    _send_arduino("OUTBOUND_FIFO_OK")
    _send_arduino("LED_R:0")
    update_yellow_led()
    return jsonify({"success": True, "new_quantity": new_qty, "slot": slot})


@app.route("/slot/base_weight", methods=["PATCH"])
def api_set_base_weight():
    """슬롯 고유 무게 설정 (출고 수량 계산 기준값)"""
    weight = request.json.get("base_weight_gram") if request.json else None
    if weight is None:
        return jsonify({"error": "base_weight_gram required"}), 400
    database.set_slot_base_weight(1, float(weight))
    return jsonify({"success": True, "base_weight_gram": float(weight)})


@app.route("/slot/resolve", methods=["POST"])
def api_resolve_slot():
    """앱에서 진열 수정 완료 후 CONFIRM 상태 해소 및 빨간 LED 끄기"""
    database.resolve_slot_confirm()
    _send_arduino("LED_R:0")
    return jsonify({"success": True, "slot": database.get_slot_status()})


@app.route("/expiring", methods=["GET"])
def api_expiring():
    days = int(request.args.get("days", 3))
    return jsonify(database.get_expiring_foods(days))


# ── 진입점 ──────────────────────────────────────────────
@app.route("/dashboard", methods=["GET"])
def api_dashboard():
    foods = database.get_all_foods()
    expiring = database.get_expiring_foods(days=3)
    return jsonify({
        "total": sum(int(f.get("quantity") or 1) for f in foods),
        "expiring_soon": len(expiring),
        "temp": latest_temp,
        "hum": latest_hum,
        "slot": database.get_slot_status(),
    })


@app.route("/scan/start", methods=["POST"])
def api_scan_start():
    threading.Thread(target=run_inbound_scan_loop, daemon=True).start()
    return jsonify({"success": True})


if __name__ == "__main__":
    database.init_db()

    threading.Thread(target=arduino_listener, daemon=True).start()

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(expiry_alert_job, "cron", hour="9,15", minute=0)
    scheduler.start()

    print("[Server] http://0.0.0.0:5000 시작")
    app.run(host="0.0.0.0", port=5000)
