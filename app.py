
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
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)

st.set_page_config(
    page_title="Quản lý tiền phòng trọ",
    page_icon="🏠",
    layout="wide"
)

STATUS = ["Chưa đóng tiền", "Đã đóng tiền"]
DB_PATH = os.getenv("TRO_DB_PATH", "quan_ly_tro.db")


# =========================================
# DATABASE SQLITE
# =========================================

def connect():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY,
                tenant_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                default_rent INTEGER NOT NULL DEFAULT 2500000
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                tenant_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                rent INTEGER NOT NULL DEFAULT 2500000,
                old_electric INTEGER NOT NULL DEFAULT 0,
                new_electric INTEGER NOT NULL DEFAULT 0,
                old_water INTEGER NOT NULL DEFAULT 0,
                new_water INTEGER NOT NULL DEFAULT 0,
                electric_price INTEGER NOT NULL DEFAULT 3500,
                water_price INTEGER NOT NULL DEFAULT 15000,
                other_fee INTEGER NOT NULL DEFAULT 150000,
                status TEXT NOT NULL DEFAULT 'Chưa đóng tiền',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (year, month, room_id)
            )
        """)


def get_room(room_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM rooms WHERE room_id = ?",
            (room_id,)
        ).fetchone()

    if row:
        return dict(row)

    return {
        "room_id": room_id,
        "tenant_name": "",
        "phone": "",
        "default_rent": 2500000
    }


def get_bill(year, month, room_id):
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM bills
               WHERE year = ? AND month = ? AND room_id = ?""",
            (year, month, room_id)
        ).fetchone()

    return dict(row) if row else None


def get_month_bills(year, month):
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM bills
               WHERE year = ? AND month = ?
               ORDER BY room_id""",
            (year, month)
        ).fetchall()

    return [dict(row) for row in rows]


def previous_period(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def defaults(year, month, room_id,
             electric_price, water_price, other_fee):

    room = get_room(room_id)
    prev_year, prev_month = previous_period(year, month)
    previous = get_bill(prev_year, prev_month, room_id)

    old_e = previous["new_electric"] if previous else 0
    old_w = previous["new_water"] if previous else 0

    return {
        "year": year,
        "month": month,
        "room_id": room_id,
        "tenant_name": room["tenant_name"],
        "phone": room["phone"],
        "rent": room["default_rent"],
        "old_electric": old_e,
        "new_electric": old_e,
        "old_water": old_w,
        "new_water": old_w,
        "electric_price": electric_price,
        "water_price": water_price,
        "other_fee": other_fee,
        "status": STATUS[0]
    }


def save_bill(bill):
    columns = (
        "year", "month", "room_id",
        "tenant_name", "phone", "rent",
        "old_electric", "new_electric",
        "old_water", "new_water",
        "electric_price", "water_price",
        "other_fee", "status"
    )

    values = [bill[k] for k in columns]

    with connect() as conn:
        conn.execute("""
            INSERT INTO rooms (
                room_id, tenant_name, phone, default_rent
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                tenant_name = excluded.tenant_name,
                phone = excluded.phone,
                default_rent = excluded.default_rent
        """, (
            bill["room_id"],
            bill["tenant_name"],
            bill["phone"],
            bill["rent"]
        ))

        placeholders = ", ".join(["?"] * len(columns))
        column_names = ", ".join(columns)

        updates = ", ".join(
            f"{c} = excluded.{c}"
            for c in columns
            if c not in ("year", "month", "room_id")
        )

        conn.execute(
            f"""
            INSERT INTO bills ({column_names})
            VALUES ({placeholders})
            ON CONFLICT(year, month, room_id)
            DO UPDATE SET
                {updates},
                updated_at = CURRENT_TIMESTAMP
            """,
            values
        )


# =========================================
# TINH TOAN
# =========================================

def calculate(bill):
    electric_usage = (
        bill["new_electric"] - bill["old_electric"]
    )
    water_usage = (
        bill["new_water"] - bill["old_water"]
    )

    electric_amount = (
        electric_usage * bill["electric_price"]
    )
    water_amount = (
        water_usage * bill["water_price"]
    )

    total = (
        bill["rent"]
        + electric_amount
        + water_amount
        + bill["other_fee"]
    )

    return (
        electric_usage,
        water_usage,
        electric_amount,
        water_amount,
        total
    )


def money(value):
    return f"{value:,.0f}".replace(",", ".") + " đ"


# =========================================
# XUAT PDF
# =========================================


def pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    font = "STSong-Light"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))

    return font, font


def make_pdf(bill):
    regular, bold = pdf_font()

    (
        electric_usage,
        water_usage,
        electric_amount,
        water_amount,
        total
    ) = calculate(bill)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="TroTitle",
        fontName=bold,
        fontSize=17,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
        spaceAfter=14
    ))

    styles.add(ParagraphStyle(
        name="TroText",
        fontName=regular,
        fontSize=10,
        leading=17
    ))

    styles.add(ParagraphStyle(
        name="TroBoldText",
        parent=styles["TroText"],
        fontName=bold
    ))

    styles.add(ParagraphStyle(
        name="TroRight",
        parent=styles["TroText"],
        alignment=TA_RIGHT
    ))

    def p(value, style="TroText"):
        return Paragraph(
            escape(str(value)),
            styles[style]
        )

    story = [
        p("HÓA ĐƠN TIỀN PHÒNG TRỌ", "TroTitle"),
        p(
            f"Phòng {bill['room_id']} - "
            f"Tháng {bill['month']:02d}/{bill['year']}",
            "TroBoldText"
        ),
        Spacer(1, 10),
        p(
            "Người thuê: "
            + (bill["tenant_name"] or "Chưa cập nhật")
        ),
        p(
            "Số điện thoại: "
            + (bill["phone"] or "Chưa cập nhật")
        ),
        Spacer(1, 15)
    ]

    rows = [
        [
            p("Khoản thu", "TroBoldText"),
            p("Chi tiết", "TroBoldText"),
            p("Thành tiền", "TroBoldText")
        ],
        [
            p("Tiền phòng"),
            p("Giá thuê tháng"),
            p(money(bill["rent"]), "TroRight")
        ],
        [
            p("Tiền điện"),
            p(
                f"{bill['old_electric']} → "
                f"{bill['new_electric']} kWh "
                f"({electric_usage} kWh)"
            ),
            p(money(electric_amount), "TroRight")
        ],
        [
            p("Tiền nước"),
            p(
                f"{bill['old_water']} → "
                f"{bill['new_water']} m³ "
                f"({water_usage} m³)"
            ),
            p(money(water_amount), "TroRight")
        ],
        [
            p("Phí khác"),
            p("Wifi, vệ sinh, ..."),
            p(money(bill["other_fee"]), "TroRight")
        ],
        [
            p("TỔNG CỘNG", "TroBoldText"),
            p(""),
            p(money(total), "TroRight")
        ]
    ]

    table = Table(
        rows,
        colWidths=[43 * mm, 76 * mm, 51 * mm],
        repeatRows=1,
        hAlign="LEFT"
    )

    table.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0), (-1, 0),
            colors.HexColor("#E8F0FA")
        ),
        (
            "BACKGROUND",
            (0, -1), (-1, -1),
            colors.HexColor("#EDF5EE")
        ),
        (
            "LINEBELOW",
            (0, 0), (-1, -1),
            0.35,
            colors.HexColor("#C7D2DE")
        ),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11)
    ]))

    story.extend([
        table,
        Spacer(1, 18),
        p(
            "Trạng thái: " + bill["status"],
            "TroBoldText"
        ),
        Spacer(1, 20),
        p(
            "Hóa đơn được tạo từ phần mềm quản lý tiền phòng trọ."
        )
    ])

    doc.build(story)
    buffer.seek(0)

    return buffer.getvalue()


# =========================================
# KHOI TAO
# =========================================

try:
    init_db()
except (sqlite3.Error, OSError) as exc:
    st.error("Không thể khởi tạo SQLite.")
    st.exception(exc)
    st.stop()


# =========================================
# GIAO DIEN
# =========================================

st.title(
    "🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ_VŨ ĐỨC BÌNH"
)

st.sidebar.header("⚙️ ĐƠN GIÁ ĐIỆN NƯỚC")

gia_dien = st.sidebar.number_input(
    "⚡ Giá điện (đ/kWh)",
    min_value=0,
    value=3500,
    step=100
)

gia_nuoc = st.sidebar.number_input(
    "💧 Giá nước (đ/m³)",
    min_value=0,
    value=15000,
    step=500
)

phi_khac = st.sidebar.number_input(
    "📦 Phí khác",
    min_value=0,
    value=150000,
    step=10000
)

so_phong = st.sidebar.slider(
    "Số lượng phòng",
    min_value=1,
    max_value=100,
    value=10
)

now = datetime.now()

col_nam, col_thang = st.sidebar.columns(2)

with col_nam:
    nam = st.selectbox(
        "Năm",
        list(range(now.year - 5, now.year + 6)),
        index=5
    )

with col_thang:
    thang = st.selectbox(
        "Tháng",
        list(range(1, 13)),
        index=now.month - 1,
        format_func=lambda x: f"Tháng {x}"
    )

st.sidebar.caption(
    "Đơn giá mặc định chỉ áp dụng cho hóa đơn mới."
)


# =========================================
# NHAP DU LIEU
# =========================================

st.header(f"📋 Nhập số liệu - Tháng {thang}/{nam}")

phong = st.selectbox(
    "Chọn phòng cần nhập dữ liệu",
    range(1, so_phong + 1),
    format_func=lambda x: f"Phòng {x}"
)

existing = get_bill(nam, thang, phong)

record = existing or defaults(
    nam, thang, phong,
    gia_dien, gia_nuoc, phi_khac
)

if not existing:
    st.info(
        "Phòng này chưa có hóa đơn. "
        "Nhấn Lưu để ghi dữ liệu vào SQLite."
    )

with st.form(key=f"edit_{nam}_{thang}_{phong}"):

    st.subheader(f"🏠 Cập nhật phòng {phong}")

    a, b, c = st.columns([1, 1.4, 1.2])

    with a:
        rent = st.number_input(
            "Giá phòng (VNĐ)",
            min_value=0,
            value=int(record["rent"]),
            step=50000
        )

    with b:
        tenant = st.text_input(
            "👤 Tên người ở",
            value=record["tenant_name"]
        )

    with c:
        phone = st.text_input(
            "📞 Số điện thoại",
            value=record["phone"]
        )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        old_e = st.number_input(
            "Số điện CŨ",
            min_value=0,
            value=int(record["old_electric"])
        )

    with c2:
        new_e = st.number_input(
            "Số điện MỚI",
            min_value=0,
            value=int(record["new_electric"])
        )

    with c3:
        old_w = st.number_input(
            "Số nước CŨ",
            min_value=0,
            value=int(record["old_water"])
        )

    with c4:
        new_w = st.number_input(
            "Số nước MỚI",
            min_value=0,
            value=int(record["new_water"])
        )

    d1, d2, d3, d4 = st.columns(4)

    with d1:
        e_price = st.number_input(
            "Đơn giá điện",
            min_value=0,
            value=int(record["electric_price"]),
            step=100
        )

    with d2:
        w_price = st.number_input(
            "Đơn giá nước",
            min_value=0,
            value=int(record["water_price"]),
            step=500
        )

    with d3:
        other = st.number_input(
            "Phí khác",
            min_value=0,
            value=int(record["other_fee"]),
            step=10000
        )

    with d4:
        status = st.selectbox(
            "💳 Trạng thái thanh toán",
            STATUS,
            index=(
                STATUS.index(record["status"])
                if record["status"] in STATUS
                else 0
            )
        )

    submitted = st.form_submit_button(
        "💾 LƯU DỮ LIỆU PHÒNG",
        type="primary",
        width="stretch"
    )

if submitted:
    if new_e < old_e or new_w < old_w:
        st.error(
            "Số điện/nước MỚI không được nhỏ hơn số CŨ."
        )
    else:
        bill = {
            "year": nam,
            "month": thang,
            "room_id": phong,
            "tenant_name": tenant.strip(),
            "phone": phone.strip(),
            "rent": rent,
            "old_electric": old_e,
            "new_electric": new_e,
            "old_water": old_w,
            "new_water": new_w,
            "electric_price": e_price,
            "water_price": w_price,
            "other_fee": other,
            "status": status
        }

        try:
            save_bill(bill)
            st.success(
                f"Đã lưu phòng {phong} "
                f"tháng {thang}/{nam}!"
            )
            st.rerun()
        except sqlite3.Error as exc:
            st.error("Không lưu được dữ liệu.")
            st.exception(exc)


# =========================================
# XUAT PDF THEO PHONG
# =========================================

st.divider()
st.subheader("🧾 Xuất hóa đơn PDF theo phòng")

saved = get_bill(nam, thang, phong)

if saved:
    _, _, _, _, total_room = calculate(saved)

    st.write(
        f"**Phòng {phong}** — "
        f"{saved['tenant_name'] or 'Chưa cập nhật'}"
    )

    st.metric(
        "Tổng tiền phòng này",
        money(total_room)
    )

    try:
        pdf_data = make_pdf(saved)

        st.download_button(
            "📥 TẢI HÓA ĐƠN PDF PHÒNG NÀY",
            data=pdf_data,
            file_name=(
                f"Hoa_Don_Phong_{phong}_"
                f"Thang_{thang}_{nam}.pdf"
            ),
            mime="application/pdf",
            width="stretch"
        )
    except Exception as exc:
        st.error("Không thể tạo PDF.")
        st.exception(exc)
else:
    st.info(
        "Hãy lưu dữ liệu phòng trước khi xuất PDF."
    )


# =========================================
# BANG TONG HOP
# =========================================

st.divider()
st.header(
    f"📊 Bảng tổng hợp tiền trọ - Tháng {thang}/{nam}"
)

bills = get_month_bills(nam, thang)

results = []

for bill in bills:
    if bill["room_id"] > so_phong:
        continue

    (
        electric_usage,
        water_usage,
        electric_amount,
        water_amount,
        total
    ) = calculate(bill)

    results.append({
        "Phòng": f"Phòng {bill['room_id']}",
        "Người ở": bill["tenant_name"],
        "Số điện thoại": bill["phone"],
        "Giá phòng": bill["rent"],
        "Số điện cũ": bill["old_electric"],
        "Số điện mới": bill["new_electric"],
        "Tiền điện": electric_amount,
        "Số nước cũ": bill["old_water"],
        "Số nước mới": bill["new_water"],
        "Tiền nước": water_amount,
        "Phí khác": bill["other_fee"],
        "Tổng tiền": total,
        "Trạng thái": bill["status"]
    })

if results:
    df = pd.DataFrame(results)

    total_revenue = int(df["Tổng tiền"].sum())

    paid_total = int(
        df.loc[
            df["Trạng thái"] == "Đã đóng tiền",
            "Tổng tiền"
        ].sum()
    )

    unpaid_total = total_revenue - paid_total

    m1, m2, m3 = st.columns(3)

    with m1:
        st.metric(
            "💰 Tổng tiền phải thu",
            money(total_revenue)
        )

    with m2:
        st.metric(
            "✅ Đã thu",
            money(paid_total)
        )

    with m3:
        st.metric(
            "⏳ Chưa thu",
            money(unpaid_total)
        )

    money_columns = [
        "Giá phòng",
        "Tiền điện",
        "Tiền nước",
        "Phí khác",
        "Tổng tiền"
    ]

    config = {
        col: st.column_config.NumberColumn(
            col,
            format="%d"
        )
        for col in money_columns
    }

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config=config
    )

    csv_data = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "📥 Xuất báo cáo CSV",
        data=csv_data,
        file_name=f"Bang_Tien_Phong_{thang}_{nam}.csv",
        mime="text/csv",
        width="stretch"
    )

else:
    st.info(
        "Chưa có hóa đơn nào được lưu trong tháng này."
    )


# =========================================
# THONG TIN DATABASE
# =========================================

st.sidebar.divider()

st.sidebar.caption(
    "💾 Dữ liệu được lưu trong SQLite: "
    + DB_PATH
)

st.sidebar.warning(
    "Nếu chạy trên Streamlit Community Cloud, "
    "file SQLite có thể bị mất khi ứng dụng "
    "được triển khai lại hoặc máy chủ bị thay thế. "
    "Hãy sao lưu dữ liệu thường xuyên."
)
