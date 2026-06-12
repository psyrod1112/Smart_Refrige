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
        """)
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
def confirm_outbound(food_id: int) -> int | None:
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
        conn.commit()
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


