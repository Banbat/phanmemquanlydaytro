
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

STATUS = ["Chưa đóng tiền", "Đã đóng tiền"]


@contextmanager
def connect():
    url = os.getenv("DATABASE_URL", "")
    if url:
        import psycopg
        conn = psycopg.connect(url, connect_timeout=15)
    else:
        conn = sqlite3.connect(
            os.getenv("TRO_DB_PATH", "quan_ly_tro.db"),
            timeout=20
        )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql, params=(), fetch=False):
    postgres = bool(os.getenv("DATABASE_URL"))
    with connect() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                sql.replace("?", "%s") if postgres else sql,
                params
            )
            if fetch:
                names = [c[0] for c in cur.description]
                return [
                    dict(zip(names, row))
                    for row in cur.fetchall()
                ]
        finally:
            cur.close()


def init_db():
    execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            room_id INTEGER PRIMARY KEY,
            tenant_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            default_rent INTEGER DEFAULT 2500000
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS bills (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            tenant_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            rent INTEGER DEFAULT 2500000,
            old_electric INTEGER DEFAULT 0,
            new_electric INTEGER DEFAULT 0,
            old_water INTEGER DEFAULT 0,
            new_water INTEGER DEFAULT 0,
            electric_price INTEGER DEFAULT 3500,
            water_price INTEGER DEFAULT 15000,
            other_fee INTEGER DEFAULT 150000,
            status TEXT DEFAULT 'Chưa đóng tiền',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (year, month, room_id)
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id TEXT PRIMARY KEY,
            year INTEGER,
            month INTEGER,
            room_id INTEGER,
            kind TEXT,
            sent_day TEXT,
            recipient TEXT,
            outcome TEXT,
            error TEXT,
            sent_at TEXT
        )
    """)

    # Nâng cấp database cũ, không xóa hóa đơn.
    for table in ("rooms", "bills"):
        if os.getenv("DATABASE_URL"):
            rows = execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = ?
            """, (table,), True)
            columns = {r["column_name"] for r in rows}
        else:
            rows = execute(
                f"PRAGMA table_info({table})", fetch=True
            )
            columns = {r["name"] for r in rows}

        if "email" not in columns:
            execute(
                f"ALTER TABLE {table} "
                "ADD COLUMN email TEXT DEFAULT ''"
            )


def get_room(room_id):
    rows = execute(
        "SELECT * FROM rooms WHERE room_id=?",
        (room_id,), True
    )
    return rows[0] if rows else {
        "room_id": room_id,
        "tenant_name": "",
        "phone": "",
        "email": "",
        "default_rent": 2500000
    }


def get_bill(year, month, room_id):
    rows = execute("""
        SELECT * FROM bills
        WHERE year=? AND month=? AND room_id=?
    """, (year, month, room_id), True)
    return rows[0] if rows else None


def get_bills(year, month):
    return execute("""
        SELECT * FROM bills
        WHERE year=? AND month=?
        ORDER BY room_id
    """, (year, month), True)


def default_bill(year, month, room_id, ep, wp, fee):
    room = get_room(room_id)
    py, pm = (
        (year - 1, 12)
        if month == 1 else (year, month - 1)
    )
    previous = get_bill(py, pm, room_id)
    old_e = previous["new_electric"] if previous else 0
    old_w = previous["new_water"] if previous else 0

    return {
        "year": year,
        "month": month,
        "room_id": room_id,
        "tenant_name": room["tenant_name"],
        "phone": room["phone"],
        "email": room["email"],
        "rent": room["default_rent"],
        "old_electric": old_e,
        "new_electric": old_e,
        "old_water": old_w,
        "new_water": old_w,
        "electric_price": ep,
        "water_price": wp,
        "other_fee": fee,
        "status": STATUS[0]
    }


def save_bill(b):
    fields = (
        "year", "month", "room_id", "tenant_name",
        "phone", "email", "rent", "old_electric",
        "new_electric", "old_water", "new_water",
        "electric_price", "water_price",
        "other_fee", "status"
    )

    with connect() as conn:
        postgres = bool(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        try:
            def run(sql, values):
                cur.execute(
                    sql.replace("?", "%s") if postgres else sql,
                    values
                )

            run("""
                INSERT INTO rooms
                (room_id, tenant_name, phone, email, default_rent)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(room_id) DO UPDATE SET
                tenant_name=excluded.tenant_name,
                phone=excluded.phone,
                email=excluded.email,
                default_rent=excluded.default_rent
            """, (
                b["room_id"], b["tenant_name"],
                b["phone"], b["email"], b["rent"]
            ))

            columns = ", ".join(fields)
            placeholders = ", ".join("?" for _ in fields)
            updates = ", ".join(
                f"{k}=excluded.{k}"
                for k in fields
                if k not in ("year", "month", "room_id")
            )

            run(f"""
                INSERT INTO bills ({columns})
                VALUES ({placeholders})
                ON CONFLICT(year, month, room_id)
                DO UPDATE SET
                {updates},
                updated_at=CURRENT_TIMESTAMP
            """, tuple(b[k] for k in fields))
        finally:
            cur.close()


def calculate(b):
    if (
        b["new_electric"] < b["old_electric"]
        or b["new_water"] < b["old_water"]
    ):
        raise ValueError("Chỉ số mới nhỏ hơn chỉ số cũ")

    electric = (
        b["new_electric"] - b["old_electric"]
    ) * b["electric_price"]

    water = (
        b["new_water"] - b["old_water"]
    ) * b["water_price"]

    total = b["rent"] + electric + water + b["other_fee"]
    return electric, water, total


def money(value):
    return f"{value:,.0f}".replace(",", ".") + " đ"


def log_email(b, kind, outcome, error=""):
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    execute("""
        INSERT INTO email_logs
        (id, year, month, room_id, kind, sent_day,
         recipient, outcome, error, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()),
        b["year"], b["month"], b["room_id"],
        kind, now.date().isoformat(),
        b["email"], outcome, error[:300],
        now.isoformat()
    ))


def sent_today(b, kind):
    day = datetime.now(
        ZoneInfo("Asia/Ho_Chi_Minh")
    ).date().isoformat()

    rows = execute("""
        SELECT id FROM email_logs
        WHERE year=? AND month=? AND room_id=?
        AND kind=? AND sent_day=?
        AND recipient=? AND outcome='success'
        LIMIT 1
    """, (
        b["year"], b["month"], b["room_id"],
        kind, day, b["email"]
    ), True)
    return bool(rows)


def get_logs(year, month):
    return execute("""
        SELECT * FROM email_logs
        WHERE year=? AND month=?
        ORDER BY sent_at DESC
    """, (year, month), True)
