import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = str(Path(__file__).with_name("food.db"))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS food_types (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                weight_min  REAL    NOT NULL,
                weight_max  REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS food_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                food_type_id    INTEGER REFERENCES food_types(id),
                food_type_name  TEXT,
                expired_date    DATE    NOT NULL,
                quantity        INTEGER DEFAULT 1,
                storage         TEXT    DEFAULT '냉장',
                image_id        TEXT    DEFAULT 'NONE',
                slot_number     INTEGER,
                status          TEXT    DEFAULT 'stored',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        if conn.execute("SELECT COUNT(*) FROM food_types").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO food_types (name, weight_min, weight_max) VALUES (?,?,?)",
                [
                    ("FoodType_1",  50,  150),
                    ("FoodType_2", 150,  250),
                    ("FoodType_3", 250,  380),
                    ("FoodType_4", 380,  600),
                    ("FoodType_5", 600, 1200),
                ]
            )
    print("[DB] Initialized")

def get_food_type_by_weight(weight: float) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM food_types WHERE weight_min <= ? AND ? < weight_max",
            (weight, weight)
        ).fetchone()
        if row:
            return dict(row)
        # 범위 밖이면 가장 가까운 버킷
        row = conn.execute(
            "SELECT * FROM food_types ORDER BY ABS(weight_min - ?) LIMIT 1",
            (weight,)
        ).fetchone()
        return dict(row) if row else {"id": None, "name": "Unknown"}

def insert_food_item(food_type_id, food_type_name, expired_date: datetime,
                     weight: float, storage: str, slot_number: int,
                     image_id: str = "NONE", quantity: int = 1) -> int:
    with get_conn() as conn:
        conn.execute(
            """UPDATE food_items
               SET slot_number = slot_number + 1
               WHERE status='stored' AND slot_number >= ?""",
            (slot_number,)
        )
        cur = conn.execute(
            """INSERT INTO food_items
               (food_type_id, food_type_name, expired_date, quantity, weight, storage, slot_number, image_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (food_type_id, food_type_name,
             expired_date.strftime("%Y-%m-%d"), quantity, weight, storage, slot_number, image_id)
        )
        return cur.lastrowid

def get_stored_items_by_expiry():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM food_items WHERE status='stored' ORDER BY expired_date ASC"
        ).fetchall()
        return [dict(r) for r in rows]

def update_status(item_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE food_items SET status=? WHERE id=?", (status, item_id))
        if status != "stored":
            _renumber_stored_slots(conn)

def mark_next_outgoing(status: str = "consumed"):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id FROM food_items
               WHERE status='stored'
               ORDER BY expired_date ASC, created_at ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return None
        item_id = row["id"]
        conn.execute("UPDATE food_items SET status=? WHERE id=?", (status, item_id))
        _renumber_stored_slots(conn)
        saved = conn.execute("SELECT * FROM food_items WHERE id=?", (item_id,)).fetchone()
        return dict(saved) if saved else None

def get_all_stored():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM food_items WHERE status='stored' ORDER BY expired_date ASC"
        ).fetchall()
        return [dict(r) for r in rows]

def get_dashboard(temp=None, hum=None):
    with get_conn() as conn:
        total    = conn.execute(
            "SELECT COUNT(*) FROM food_items WHERE status='stored'"
        ).fetchone()[0]
        expiring = conn.execute(
            """SELECT COUNT(*) FROM food_items
               WHERE status='stored'
               AND julianday(expired_date) - julianday('now') <= 3"""
        ).fetchone()[0]
    return {"total": total, "expiring_soon": expiring, "temp": temp, "hum": hum}

def update_food_type_name(type_id: int, name: str):
    with get_conn() as conn:
        conn.execute("UPDATE food_types SET name=? WHERE id=?", (name, type_id))

def get_all_food_types():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM food_types ORDER BY weight_min").fetchall()
        return [dict(r) for r in rows]

def _renumber_stored_slots(conn):
    rows = conn.execute(
        """SELECT id FROM food_items
           WHERE status='stored'
           ORDER BY expired_date ASC, created_at ASC"""
    ).fetchall()
    for slot, row in enumerate(rows, start=1):
        conn.execute(
            "UPDATE food_items SET slot_number=? WHERE id=?",
            (slot, row["id"])
        )
