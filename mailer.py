
import io
import os
import re
import smtplib
import unicodedata
from email.message import EmailMessage
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle
)

from core import calculate, money, log_email, sent_today


def plain(text):
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )


def make_pdf(b):
    electric, water, total = calculate(b)

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=20 * mm,
        rightMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    def p(text, style="Normal"):
        return Paragraph(
            escape(plain(text)),
            styles[style]
        )

    story = [
        p("HOA DON TIEN PHONG TRO", "Title"),
        Spacer(1, 15),
        p(f"Phong: {b['room_id']}"),
        p(f"Thang: {b['month']}/{b['year']}"),
        p(f"Nguoi thue: {b['tenant_name']}"),
        p(f"So dien thoai: {b['phone']}"),
        Spacer(1, 15)
    ]

    rows = [
        ["Khoan thu", "Thanh tien"],
        ["Tien phong", money(b["rent"])],
        [
            f"Dien: {b['old_electric']} - {b['new_electric']}",
            money(electric)
        ],
        [
            f"Nuoc: {b['old_water']} - {b['new_water']}",
            money(water)
        ],
        ["Phi khac", money(b["other_fee"])],
        ["TONG CONG", money(total)]
    ]

    rows = [
        [p(cell) for cell in row]
        for row in rows
    ]

    table = Table(
        rows,
        colWidths=[100 * mm, 65 * mm]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))

    story.extend([
        table,
        Spacer(1, 18),
        p("Trang thai: " + b["status"]),
        Spacer(1, 20),
        p("Cam on quy khach!")
    ])

    doc.build(story)
    return output.getvalue()


def valid_email(address):
    return bool(re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+",
        address.strip()
    ))


def send_email(b, kind="invoice", allow_repeat=False):
    address = (b["email"] or "").strip()

    if not valid_email(address):
        return False, "Email người thuê không hợp lệ."

    if kind not in ("invoice", "reminder"):
        return False, "Loại email không hợp lệ."

    if (
        kind == "reminder"
        and b["status"] == "Đã đóng tiền"
    ):
        return False, "Phòng đã thanh toán."

    if not allow_repeat and sent_today(b, kind):
        return False, "Email này đã được gửi hôm nay."

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("MAIL_FROM", user)

    if not user or not password:
        return False, "Chưa cấu hình SMTP."

    try:
        _, _, total = calculate(b)

        if kind == "reminder":
            subject = (
                f"Nhac thanh toan phong {b['room_id']} "
                f"- Thang {b['month']}/{b['year']}"
            )
            intro = (
                "Đây là email nhắc thanh toán tiền phòng. "
                "Nếu đã thanh toán, vui lòng liên hệ quản lý.\n\n"
            )
        else:
            subject = (
                f"Hoa don phong {b['room_id']} "
                f"- Thang {b['month']}/{b['year']}"
            )
            intro = "Thông tin hóa đơn tiền phòng của bạn:\n\n"

        content = (
            f"Kính gửi {b['tenant_name'] or 'quý khách'},\n\n"
            + intro
            + f"Phòng: {b['room_id']}\n"
            + f"Tháng: {b['month']}/{b['year']}\n"
            + f"Tổng tiền: {money(total)}\n"
            + f"Trạng thái: {b['status']}\n\n"
            + "Hóa đơn PDF được đính kèm.\n\n"
            + "Trân trọng."
        )

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = address
        msg["Subject"] = subject
        msg.set_content(content)

        pdf = make_pdf(b)

        msg.add_attachment(
            pdf,
            maintype="application",
            subtype="pdf",
            filename=(
                f"Hoa_don_phong_{b['room_id']}_"
                f"{b['month']}_{b['year']}.pdf"
            )
        )

        if port == 465:
            with smtplib.SMTP_SSL(
                host, port, timeout=30
            ) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(
                host, port, timeout=30
            ) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)

        log_email(b, kind, "success")
        return True, "Đã gửi email thành công!"

    except Exception as exc:
        try:
            log_email(b, kind, "failed", type(exc).__name__)
        except Exception:
            pass
        return False, (
            f"Gửi thất bại: {type(exc).__name__}. "
            "Kiểm tra SMTP hoặc nhật ký hệ thống."
        )
