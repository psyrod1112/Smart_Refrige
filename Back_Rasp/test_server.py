"""
PC test server — runs without Raspberry Pi hardware
No picamera2 / RPi.GPIO required.

Run:
  pip install flask flask-cors pyserial
  python test_server.py           # auto-detect serial port
  python test_server.py COM3      # specify Windows COM port
  python test_server.py /dev/ttyUSB0   # specify Linux port

Set Flutter _baseUrl in api_service.dart:
  http://<this PC's local IP>:5000
  (run ipconfig on Windows to find your IP)

Test flow (no hardware needed):
  1. POST /test/trigger_ocr       {"expired_date":"2026-12-31"}
  2. POST /test/mock_switch        {"weight":200,"temp":5}

Test flow (with Arduino connected):
  1. POST /test/trigger_ocr       {"expired_date":"2026-12-31"}
     -> Arduino receives STATE:WEIGHT_READY
  2. Open fridge door, press weight switch on Arduino
     -> Arduino sends SWITCH:weight,T:temp,H:hum
     -> Server saves to DB automatically

Other test endpoints:
  POST /test/simulate_close_weight  {"weight":320.5}
  POST /test/send_cmd               {"cmd":"LED_R:1"}
"""

import sys, os, platform, signal, atexit, threading, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
import serial
import db, fifo

app = Flask(__name__)
CORS(app)

# ── Serial port ────────────────────────────────────────────────
def _default_port():
    return 'COM3' if platform.system() == 'Windows' else '/dev/ttyUSB0'

SERIAL_PORT = sys.argv[1] if len(sys.argv) > 1 else _default_port()
BAUD_RATE   = 9600

# ── Shared state ───────────────────────────────────────────────
_ser                = None
_lock               = threading.Lock()
_current_expiry     = None
_last_temp          = None
_last_hum           = None
_last_closed_weight = None
WEIGHT_CHANGE_THRESHOLD = 30.0

# ── Logging helper with timestamp ──────────────────────────────
def log(tag: str, msg: str):
    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{ts}][{tag:<8}] {msg}", flush=True)

# ── Serial send (logs every TX) ────────────────────────────────
def send(cmd: str):
    with _lock:
        if _ser and _ser.is_open:
            _ser.write((cmd + '\n').encode())
            log('TX', cmd)
        else:
            log('TX', f'(no serial) {cmd}')

# ── Storage zone from temperature ──────────────────────────────
def storage_from_temp(temp: float) -> str:
    if temp == -99: return '냉장'
    if temp < -5:   return '냉동'
    if temp < 12:   return '냉장'
    return '상온'

# ── CLOSE_WEIGHT handler ───────────────────────────────────────
def handle_close_weight(weight: float):
    global _last_closed_weight
    if _last_closed_weight is None:
        _last_closed_weight = weight
        log('Weight', f'Base weight saved: {weight:.1f}g')
        return
    delta = weight - _last_closed_weight
    _last_closed_weight = weight
    if abs(delta) < WEIGHT_CHANGE_THRESHOLD:
        log('Weight', f'No significant change: {weight:.1f}g  delta={delta:+.1f}g  (threshold={WEIGHT_CHANGE_THRESHOLD}g)')
    elif delta < 0:
        log('Weight', f'[Outgoing?] Decreased by {-delta:.1f}g  now={weight:.1f}g')
    else:
        log('Weight', f'[Incoming?] Increased by {delta:.1f}g  now={weight:.1f}g')

# ── Serial receive loop (logs every RX line raw) ───────────────
def _read_loop():
    global _current_expiry, _last_temp, _last_hum
    while True:
        try:
            line = _ser.readline().decode(errors='ignore').strip()
            if not line:
                continue

            log('RX', line)   # every raw line from Arduino

            if line.startswith('DOOR:'):
                state = 'OPEN' if line.split(':')[1] == '1' else 'CLOSED'
                log('Door', state)

            elif line.startswith('CLOSE_WEIGHT:'):
                w = float(line.split(':')[1])
                handle_close_weight(w)

            elif line.startswith('SWITCH:'):
                parts  = line[len('SWITCH:'):].split(',')
                weight = float(parts[0])
                temp   = float(parts[1].split(':')[1])
                hum    = float(parts[2].split(':')[1])
                log('Switch', f'weight={weight:.1f}g  temp={temp}C  hum={hum}%')

                expiry = _current_expiry
                if expiry is None:
                    log('Switch', 'No OCR result -- call POST /test/trigger_ocr first')
                    continue

                food_type = db.get_food_type_by_weight(weight)
                storage   = storage_from_temp(temp)
                slot      = fifo.calc_slot(expiry)
                item_id   = db.insert_food_item(
                    food_type_id   = food_type['id'],
                    food_type_name = food_type['name'],
                    expired_date   = expiry,
                    weight         = weight,
                    storage        = storage,
                    slot_number    = slot
                )
                log('Switch', f'Saved to DB  id={item_id}  type={food_type["name"]}  storage={storage}  expiry={expiry.date()}  slot={slot}')
                send(f'OLED:Slot {slot}')
                _current_expiry = None

            elif line.startswith('TEMP:'):
                parts      = line.split(',')
                _last_temp = float(parts[0].split(':')[1])
                _last_hum  = float(parts[1].split(':')[1])
                log('DHT', f'temp={_last_temp}C  hum={_last_hum}%')

        except Exception as e:
            log('Serial', f'Read error: {e}')
            time.sleep(0.1)

# ── HTTP request logging ───────────────────────────────────────
@app.before_request
def _log_request():
    body = request.get_data(as_text=True)[:300]
    log('HTTP', f'{request.method} {request.path}' + (f'  {body}' if body else ''))

# ── Test-only endpoints ────────────────────────────────────────
@app.route('/test/trigger_ocr', methods=['POST'])
def trigger_ocr():
    """Simulate OCR success. Body: {"expired_date": "2026-12-31"}"""
    global _current_expiry
    date_str = (request.json or {}).get('expired_date', '2026-12-31')
    _current_expiry = datetime.strptime(date_str, '%Y-%m-%d')
    log('Test', f'OCR simulated: expiry={date_str}  --> sending STATE:WEIGHT_READY to Arduino')
    send('LED_R:0')
    send('STATE:WEIGHT_READY')
    return jsonify({'ok': True, 'expired_date': date_str})

@app.route('/test/mock_switch', methods=['POST'])
def mock_switch():
    """Simulate full switch+weight flow without any hardware.
    Must call /test/trigger_ocr first.
    Body (optional): {"weight": 200.0, "temp": 5.0, "hum": 65.0}
    """
    global _current_expiry
    expiry = _current_expiry
    if expiry is None:
        return jsonify({'error': 'Call /test/trigger_ocr first'}), 400

    data   = request.json or {}
    weight = float(data.get('weight', 200.0))
    temp   = float(data.get('temp',   5.0))
    log('Test', f'Mock switch: weight={weight}g  temp={temp}C')

    food_type = db.get_food_type_by_weight(weight)
    storage   = storage_from_temp(temp)
    slot      = fifo.calc_slot(expiry)
    item_id   = db.insert_food_item(
        food_type_id   = food_type['id'],
        food_type_name = food_type['name'],
        expired_date   = expiry,
        weight         = weight,
        storage        = storage,
        slot_number    = slot
    )
    _current_expiry = None
    send(f'OLED:Slot {slot}')
    log('Test', f'Saved to DB  id={item_id}  slot={slot}  type={food_type["name"]}')
    return jsonify({'id': item_id, 'slot': slot, 'food_type': food_type['name'],
                    'storage': storage, 'expired_date': str(expiry.date())})

@app.route('/test/simulate_close_weight', methods=['POST'])
def simulate_close_weight():
    """Simulate a door-close CLOSE_WEIGHT event.
    Body (optional): {"weight": 320.5}
    """
    data   = request.json or {}
    weight = float(data.get('weight', 0.0))
    log('Test', f'Simulating CLOSE_WEIGHT:{weight:.1f}g')
    handle_close_weight(weight)
    return jsonify({'ok': True, 'weight': weight,
                    'base': _last_closed_weight})

@app.route('/test/send_cmd', methods=['POST'])
def send_cmd_route():
    """Send any raw command to Arduino. Body: {"cmd": "LED_R:1"}"""
    cmd = (request.json or {}).get('cmd', '')
    if not cmd:
        return jsonify({'error': 'cmd required'}), 400
    send(cmd)
    return jsonify({'ok': True, 'sent': cmd})

@app.route('/test/status', methods=['GET'])
def test_status():
    """Check current shared state."""
    return jsonify({
        'serial_connected':   _ser is not None and _ser.is_open,
        'serial_port':        SERIAL_PORT,
        'current_expiry':     str(_current_expiry.date()) if _current_expiry else None,
        'last_temp':          _last_temp,
        'last_hum':           _last_hum,
        'last_closed_weight': _last_closed_weight,
    })

# ── Standard REST API ──────────────────────────────────────────
@app.route('/foods', methods=['GET'])
def get_foods():
    return jsonify(db.get_all_stored())

@app.route('/foods', methods=['POST'])
def add_food_manual():
    data = request.json or {}
    try:
        expiry  = datetime.strptime(data['expired_date'], '%Y-%m-%d')
        slot    = fifo.calc_slot(expiry)
        item_id = db.insert_food_item(
            food_type_id   = data.get('food_type_id'),
            food_type_name = data.get('food_type_name', 'manual'),
            expired_date   = expiry,
            weight         = float(data.get('weight', 0)),
            storage        = data.get('storage', '냉장'),
            quantity       = int(data.get('quantity', 1)),
            slot_number    = slot,
            image_id       = 'NONE'
        )
        log('API', f'Manual incoming saved  id={item_id}  name={data.get("food_type_name")}  slot={slot}')
        return jsonify({'id': item_id, 'slot': slot}), 201
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400

@app.route('/foods/<int:item_id>', methods=['PUT'])
def update_food(item_id):
    status_map = {'소비': 'consumed', '폐기': 'discarded', '이동': 'moved'}
    raw    = (request.json or {}).get('status', 'consumed')
    status = status_map.get(raw, raw)
    db.update_status(item_id, status)
    log('API', f'Outgoing  id={item_id}  status={status}')
    return jsonify({'ok': True})

@app.route('/food_types', methods=['GET'])
def get_food_types():
    return jsonify(db.get_all_food_types())

@app.route('/food_types/<int:type_id>', methods=['PUT'])
def update_food_type(type_id):
    name = (request.json or {}).get('name', '')
    if not name:
        return jsonify({'error': 'name required'}), 400
    db.update_food_type_name(type_id, name)
    return jsonify({'ok': True})

@app.route('/dashboard', methods=['GET'])
def dashboard():
    return jsonify(db.get_dashboard(_last_temp, _last_hum))

# ── Server start ───────────────────────────────────────────────
if __name__ == '__main__':
    def cleanup():
        if _ser and _ser.is_open:
            _ser.close()
            log('Serial', 'Port closed')

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
        log('Serial', f'Connected: {SERIAL_PORT}  baud={BAUD_RATE}')
        threading.Thread(target=_read_loop, daemon=True).start()
    except Exception as e:
        log('Serial', f'Connection failed ({SERIAL_PORT}): {e}')
        log('Serial', 'Running in API-only mode -- no Arduino data')
        if platform.system() == 'Windows':
            log('Serial', 'Tip: check Device Manager for the correct COM port')
            log('Serial', '     run: python test_server.py COM4')

    print()
    log('Server', 'http://localhost:5000')
    log('Server', '--- Test endpoints ---')
    log('Server', '  GET  /test/status')
    log('Server', '  POST /test/trigger_ocr           {"expired_date":"2026-12-31"}')
    log('Server', '  POST /test/mock_switch            {"weight":200,"temp":5}')
    log('Server', '  POST /test/simulate_close_weight  {"weight":320}')
    log('Server', '  POST /test/send_cmd               {"cmd":"LED_R:1"}')
    log('Server', '--- Standard API ---')
    log('Server', '  GET  /foods')
    log('Server', '  POST /foods')
    log('Server', '  PUT  /foods/<id>')
    log('Server', '  GET  /dashboard')
    print()
    app.run(host='0.0.0.0', port=5000, debug=False)
