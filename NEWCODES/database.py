import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "fridge.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS food_items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                food_id       TEXT,
                name          TEXT NOT NULL DEFAULT 'Unknown',
                food_type     TEXT,
                expiry_date   TEXT,
                weight_gram   REAL,
                quantity      INTEGER DEFAULT 1,
                registered_at TEXT,
                deleted_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS weight_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type   TEXT,
                delta        REAL,
                food_item_id INTEGER,
                created_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS notification_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at    TEXT,
                notif_type TEXT
            );
            CREATE TABLE IF NOT EXISTS fcm_tokens (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS slot_status (
                slot_id          INTEGER PRIMARY KEY,
                status           TEXT NOT NULL DEFAULT 'FIFO',
                confirm_delta    REAL DEFAULT 0,
                confirm_type     TEXT DEFAULT 'OUTBOUND',
                base_weight_gram REAL DEFAULT NULL,
                updated_at       TEXT
            );
        """)
        # 기존 DB에 새 컬럼 추가 (이미 존재하면 무시)
        for stmt in [
            "ALTER TABLE slot_status ADD COLUMN confirm_type TEXT DEFAULT 'OUTBOUND'",
            "ALTER TABLE slot_status ADD COLUMN base_weight_gram REAL DEFAULT NULL",
        ]:
            try:
                conn.execute(stmt)
            except Exception:
                pass
        conn.execute(
            """INSERT OR IGNORE INTO slot_status
               (slot_id, status, confirm_delta, confirm_type, updated_at)
               VALUES (1, 'FIFO', 0, 'OUTBOUND', ?)""",
            (datetime.now().isoformat(),),
        )
        conn.commit()


# ── FCM 토큰 ────────────────────────────────────────────
def get_all_tokens() -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT token FROM fcm_tokens").fetchall()
    return [r["token"] for r in rows]


def upsert_token(token: str):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO fcm_tokens (token) VALUES (?)", (token,))
        conn.commit()


# ── 식품 ────────────────────────────────────────────────
def insert_food(food_id: str, name: str, expiry_date: str,
                weight_gram: float, quantity: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO food_items
               (food_id, name, expiry_date, weight_gram, quantity, registered_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (food_id, name, expiry_date, weight_gram, quantity,
             datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def get_all_foods() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, food_type, expiry_date, weight_gram,
                      quantity, registered_at
               FROM food_items
               WHERE deleted_at IS NULL
               ORDER BY expiry_date ASC"""
        ).fetchall()
    return [dict(r) for r in rows]


def check_fifo(new_expiry: str) -> bool:
    foods = get_all_foods()
    valid_dates = [f["expiry_date"] for f in foods if f.get("expiry_date")]
    if not valid_dates:
        return True
    earliest_expiry = min(valid_dates)
    return new_expiry >= earliest_expiry



def update_food(food_id: int, fields: dict) -> bool:
    allowed = {"name", "food_type", "expiry_date", "weight_gram", "quantity"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    with get_db() as conn:
        quantity = updates.get("quantity")
        if quantity is not None and int(quantity) <= 0:
            conn.execute(
                "UPDATE food_items SET quantity=0, deleted_at=? WHERE id=?",
                (datetime.now().isoformat(), food_id),
            )
        else:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [food_id]
            conn.execute(f"UPDATE food_items SET {set_clause} WHERE id=?", values)
        conn.commit()
    return True


def get_slot_status() -> dict:
    with get_db() as conn:
        row = conn.execute(
            """SELECT slot_id, status, confirm_delta, confirm_type, base_weight_gram, updated_at
               FROM slot_status
               WHERE slot_id=1"""
        ).fetchone()
    if row:
        return dict(row)
    return {
        "slot_id": 1, "status": "FIFO", "confirm_delta": 0,
        "confirm_type": "OUTBOUND", "base_weight_gram": None, "updated_at": None,
    }


def mark_slot_confirm(delta: float = 0, confirm_type: str = "OUTBOUND") -> dict:
    now_str = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO slot_status (slot_id, status, confirm_delta, confirm_type, updated_at)
               VALUES (1, 'CONFIRM', ?, ?, ?)
               ON CONFLICT(slot_id) DO UPDATE SET
                   status='CONFIRM',
                   confirm_delta=excluded.confirm_delta,
                   confirm_type=excluded.confirm_type,
                   updated_at=excluded.updated_at""",
            (delta, confirm_type, now_str),
        )
        conn.commit()
    return get_slot_status()


def get_slot_base_weight(slot_id: int = 1) -> float | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT base_weight_gram FROM slot_status WHERE slot_id=?", (slot_id,)
        ).fetchone()
    if row and row["base_weight_gram"]:
        return float(row["base_weight_gram"])
    return None


def set_slot_base_weight(slot_id: int, weight: float):
    with get_db() as conn:
        conn.execute(
            "UPDATE slot_status SET base_weight_gram=? WHERE slot_id=?",
            (weight, slot_id),
        )
        conn.commit()


def resolve_slot_confirm() -> dict:
    now_str = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            """UPDATE slot_status
               SET status='FIFO', confirm_delta=0, updated_at=?
               WHERE slot_id=1""",
            (now_str,),
        )
        conn.commit()
    return get_slot_status()


def calculate_display_position(new_expiry: str) -> int:
    foods = get_all_foods()
    valid_dates = [f["expiry_date"] for f in foods if f.get("expiry_date")]
    valid_dates.append(new_expiry)
    valid_dates.sort()
    return valid_dates.index(new_expiry) + 1


def delete_oldest_foods(quantity: int) -> list[int]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id FROM food_items
               WHERE deleted_at IS NULL
               ORDER BY expiry_date ASC
               LIMIT ?""",
            (quantity,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        now_str = datetime.now().isoformat()
        for fid in ids:
            conn.execute(
                "UPDATE food_items SET quantity=0, deleted_at=? WHERE id=?",
                (now_str, fid),
            )
        conn.commit()
    return ids


# ── 출고 ────────────────────────────────────────────────
def confirm_outbound(food_id: int, delta: float) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT quantity FROM food_items WHERE id=?", (food_id,)
        ).fetchone()
        if not row:
            return None
        new_qty = row["quantity"] - 1
        if new_qty <= 0:
            conn.execute(
                "UPDATE food_items SET quantity=0, deleted_at=? WHERE id=?",
                (datetime.now().isoformat(), food_id),
            )
        else:
            conn.execute(
                "UPDATE food_items SET quantity=? WHERE id=?", (new_qty, food_id)
            )
        conn.execute(
            """INSERT INTO weight_logs (event_type, delta, food_item_id, created_at)
               VALUES (?,?,?,?)""",
            ("OUT", delta, food_id, datetime.now().isoformat()),
        )
        conn.commit()
    resolve_slot_confirm()
    return max(0, new_qty)


# ── 유통기한 알림 ─────────────────────────────────────
def get_expiring_foods(days: int = 3) -> list[dict]:
    cutoff = (datetime.now().date() + timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, expiry_date
               FROM food_items
               WHERE expiry_date <= ? AND deleted_at IS NULL
               ORDER BY expiry_date ASC""",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def already_notified_today(notif_type: str) -> bool:
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        row = conn.execute(
            """SELECT id FROM notification_logs
               WHERE DATE(sent_at)=? AND notif_type=? LIMIT 1""",
            (today, notif_type),
        ).fetchone()
    return row is not None


def log_notification(notif_type: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO notification_logs (sent_at, notif_type) VALUES (?,?)",
            (datetime.now().isoformat(), notif_type),
        )
        conn.commit()
