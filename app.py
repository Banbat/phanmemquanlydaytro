
import os
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Quản lý tiền phòng trọ",
    page_icon="🏠",
    layout="wide"
)

# Đọc Secrets trên Streamlit Cloud
for key in (
    "DATABASE_URL", "SMTP_HOST", "SMTP_PORT",
    "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"
):
    try:
        if key in st.secrets and not os.getenv(key):
            os.environ[key] = str(st.secrets[key])
    except (FileNotFoundError, KeyError):
        pass

from core import (
    STATUS, init_db, get_bill, get_bills,
    default_bill, save_bill, calculate,
    money, get_logs
)
from mailer import make_pdf, send_email

try:
    init_db()
except Exception as exc:
    st.error("Không kết nối được database.")
    st.exception(exc)
    st.stop()

st.title("🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ_VŨ ĐỨC BÌNH")

st.sidebar.header("⚙️ CẤU HÌNH")

gia_dien = st.sidebar.number_input(
    "Giá điện (đ/kWh)", 0, 3500, 100
)
gia_nuoc = st.sidebar.number_input(
    "Giá nước (đ/m³)", 0, 15000, 500
)
phi_khac = st.sidebar.number_input(
    "Phí khác", 0, 150000, 10000
)
so_phong = st.sidebar.slider(
    "Số lượng phòng", 1, 100, 10
)

now = datetime.now()
c1, c2 = st.sidebar.columns(2)

with c1:
    nam = st.selectbox(
        "Năm",
        list(range(now.year - 5, now.year + 6)),
        index=5
    )

with c2:
    thang = st.selectbox(
        "Tháng",
        list(range(1, 13)),
        index=now.month - 1
    )

st.header(f"📋 Quản lý tháng {thang}/{nam}")

phong = st.selectbox(
    "Chọn phòng",
    range(1, so_phong + 1),
    format_func=lambda x: f"Phòng {x}"
)

existing = get_bill(nam, thang, phong)
record = existing or default_bill(
    nam, thang, phong,
    gia_dien, gia_nuoc, phi_khac
)

with st.form(f"form_{nam}_{thang}_{phong}"):
    st.subheader(f"🏠 Phòng {phong}")

    a, b, c, d = st.columns(4)

    with a:
        rent = st.number_input(
            "Giá phòng", min_value=0,
            value=int(record["rent"]),
            step=50000
        )
    with b:
        tenant = st.text_input(
            "Tên người thuê",
            value=record["tenant_name"]
        )
    with c:
        phone = st.text_input(
            "Số điện thoại",
            value=record["phone"]
        )
    with d:
        email = st.text_input(
            "Email người thuê",
            value=record["email"]
        )

    a, b, c, d = st.columns(4)

    with a:
        old_e = st.number_input(
            "Điện cũ", min_value=0,
            value=int(record["old_electric"])
        )
    with b:
        new_e = st.number_input(
            "Điện mới", min_value=0,
            value=int(record["new_electric"])
        )
    with c:
        old_w = st.number_input(
            "Nước cũ", min_value=0,
            value=int(record["old_water"])
        )
    with d:
        new_w = st.number_input(
            "Nước mới", min_value=0,
            value=int(record["new_water"])
        )

    a, b, c, d = st.columns(4)

    with a:
        ep = st.number_input(
            "Đơn giá điện", min_value=0,
            value=int(record["electric_price"])
        )
    with b:
        wp = st.number_input(
            "Đơn giá nước", min_value=0,
            value=int(record["water_price"])
        )
    with c:
        fee = st.number_input(
            "Phí khác", min_value=0,
            value=int(record["other_fee"])
        )
    with d:
        status = st.selectbox(
            "Trạng thái thanh toán",
            STATUS,
            index=(
                STATUS.index(record["status"])
                if record["status"] in STATUS else 0
            )
        )

    submitted = st.form_submit_button(
        "💾 LƯU DỮ LIỆU",
        type="primary",
        width="stretch"
    )

if submitted:
    data = {
        "year": nam,
        "month": thang,
        "room_id": phong,
        "tenant_name": tenant.strip(),
        "phone": phone.strip(),
        "email": email.strip(),
        "rent": rent,
        "old_electric": old_e,
        "new_electric": new_e,
        "old_water": old_w,
        "new_water": new_w,
        "electric_price": ep,
        "water_price": wp,
        "other_fee": fee,
        "status": status
    }

    try:
        calculate(data)
        save_bill(data)
        st.success("Đã lưu dữ liệu!")
        st.rerun()
    except Exception as exc:
        st.error(f"Lỗi lưu dữ liệu: {exc}")

st.divider()
st.header("📧 GỬI HÓA ĐƠN QUA EMAIL")

saved = get_bill(nam, thang, phong)

if saved:
    _, _, total = calculate(saved)

    st.write(
        f"**Người thuê:** {saved['tenant_name']}"
    )
    st.write(
        f"**Email:** {saved['email'] or 'Chưa có email'}"
    )
    st.metric("Tổng tiền phòng", money(total))

    a, b, c = st.columns(3)

    with a:
        pdf = make_pdf(saved)
        st.download_button(
            "📥 TẢI PDF",
            data=pdf,
            file_name=(
                f"Hoa_don_{phong}_{thang}_{nam}.pdf"
            ),
            mime="application/pdf",
            width="stretch"
        )

    with b:
        if st.button(
            "📤 GỬI HÓA ĐƠN",
            width="stretch"
        ):
            ok, message = send_email(
                saved, "invoice", allow_repeat=True
            )
            if ok:
                st.success(message)
            else:
                st.error(message)

    with c:
        if st.button(
            "🔔 NHẮC THANH TOÁN",
            disabled=saved["status"] == "Đã đóng tiền",
            width="stretch"
        ):
            ok, message = send_email(
                saved, "reminder"
            )
            if ok:
                st.success(message)
            else:
                st.error(message)
else:
    st.info("Lưu dữ liệu phòng trước khi gửi email.")

st.divider()
st.header(f"📊 TỔNG HỢP THÁNG {thang}/{nam}")

all_bills = get_bills(nam, thang)
rows = []

for item in all_bills:
    if item["room_id"] > so_phong:
        continue

    electric, water, total = calculate(item)

    rows.append({
        "Phòng": item["room_id"],
        "Người thuê": item["tenant_name"],
        "Email": item["email"],
        "Giá phòng": item["rent"],
        "Điện cũ": item["old_electric"],
        "Điện mới": item["new_electric"],
        "Tiền điện": electric,
        "Nước cũ": item["old_water"],
        "Nước mới": item["new_water"],
        "Tiền nước": water,
        "Phí khác": item["other_fee"],
        "Tổng tiền": total,
        "Trạng thái": item["status"]
    })

if rows:
    df = pd.DataFrame(rows)

    total_due = sum(x["Tổng tiền"] for x in rows)
    total_paid = sum(
        x["Tổng tiền"] for x in rows
        if x["Trạng thái"] == "Đã đóng tiền"
    )

    a, b, c = st.columns(3)
    a.metric("💰 Tổng phải thu", money(total_due))
    b.metric("✅ Đã thu", money(total_paid))
    c.metric("⏳ Chưa thu", money(total_due - total_paid))

    st.dataframe(
        df, width="stretch", hide_index=True
    )

    st.download_button(
        "📥 Xuất CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"Bao_cao_{thang}_{nam}.csv",
        mime="text/csv"
    )

    if st.button("📨 GỬI HÓA ĐƠN TẤT CẢ PHÒNG"):
        success = 0
        failed = 0

        for item in all_bills:
            if not item["email"].strip():
                continue

            ok, message = send_email(
                item, "invoice"
            )
            if ok:
                success += 1
            else:
                failed += 1

        st.info(
            f"Gửi thành công: {success} | "
            f"Thất bại hoặc bỏ qua: {failed}"
        )
else:
    st.info("Chưa có hóa đơn tháng này.")

with st.expander("📜 Lịch sử gửi email"):
    history = get_logs(nam, thang)
    if history:
        st.dataframe(
            pd.DataFrame(history),
            width="stretch",
            hide_index=True
        )
    else:
        st.write("Chưa có lịch sử gửi email.")
