import io
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

DB_PATH = Path(os.getenv('TRO_DB_PATH', str(Path(__file__).with_name('quan_ly_tro.db'))))
STATUS = ('Chưa đóng tiền', 'Đã đóng tiền')

st.set_page_config(page_title='Quản lý tiền phòng trọ', page_icon='🏠', layout='wide')


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=20000')
    return conn


def init_db():
    with connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS rooms (
            room_id INTEGER PRIMARY KEY, tenant_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '', default_rent INTEGER NOT NULL DEFAULT 2500000
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS bills (
            year INTEGER NOT NULL, month INTEGER NOT NULL, room_id INTEGER NOT NULL,
            tenant_name TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
            rent INTEGER NOT NULL, old_electric INTEGER NOT NULL, new_electric INTEGER NOT NULL,
            old_water INTEGER NOT NULL, new_water INTEGER NOT NULL,
            electric_price INTEGER NOT NULL, water_price INTEGER NOT NULL,
            other_fee INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Chưa đóng tiền',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (year, month, room_id)
        )''')


def get_room(room_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM rooms WHERE room_id=?', (room_id,)).fetchone()
    return dict(row) if row else {'room_id': room_id, 'tenant_name': '', 'phone': '', 'default_rent': 2500000}


def get_bill(year, month, room_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM bills WHERE year=? AND month=? AND room_id=?',
                           (year, month, room_id)).fetchone()
    return dict(row) if row else None


def previous_period(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def defaults(year, month, room_id, electric_price, water_price, other_fee):
    room = get_room(room_id)
    prev_year, prev_month = previous_period(year, month)
    previous = get_bill(prev_year, prev_month, room_id)
    old_e = previous['new_electric'] if previous else 0
    old_w = previous['new_water'] if previous else 0
    return dict(year=year, month=month, room_id=room_id,
                tenant_name=room['tenant_name'], phone=room['phone'], rent=room['default_rent'],
                old_electric=old_e, new_electric=old_e, old_water=old_w, new_water=old_w,
                electric_price=electric_price, water_price=water_price,
                other_fee=other_fee, status=STATUS[0])


def save_bill(bill):
    columns = ('year', 'month', 'room_id', 'tenant_name', 'phone', 'rent',
               'old_electric', 'new_electric', 'old_water', 'new_water',
               'electric_price', 'water_price', 'other_fee', 'status')
    values = [bill[k] for k in columns]
    with connect() as conn:
        conn.execute('''INSERT INTO rooms(room_id, tenant_name, phone, default_rent)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(room_id) DO UPDATE SET
                        tenant_name=excluded.tenant_name, phone=excluded.phone,
                        default_rent=excluded.default_rent''',
                     (bill['room_id'], bill['tenant_name'], bill['phone'], bill['rent']))
        conn.execute(f'''INSERT INTO bills ({', '.join(columns)})
                        VALUES ({', '.join(['?'] * len(columns))})
                        ON CONFLICT(year, month, room_id) DO UPDATE SET
                        {', '.join(f'{c}=excluded.{c}' for c in columns if c not in ('year', 'month', 'room_id'))},
                        updated_at=CURRENT_TIMESTAMP''', values)
