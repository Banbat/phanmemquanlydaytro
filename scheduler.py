
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from core import init_db, get_bills
from mailer import send_email


def main():
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "Cần DATABASE_URL dùng chung để gửi tự động."
        )

    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    reminder_day = int(os.getenv("REMINDER_DAY", "5"))

    if now.day != reminder_day:
        print("Hôm nay không phải ngày gửi nhắc.")
        return

    # Nhắc tiền phòng của tháng trước
    if now.month == 1:
        year, month = now.year - 1, 12
    else:
        year, month = now.year, now.month - 1

    init_db()

    count = 0

    for bill in get_bills(year, month):
        if bill["status"] != "Chưa đóng tiền":
            continue

        if not bill["email"].strip():
            continue

        success, message = send_email(
            bill, "reminder"
        )

        print(f"Phòng {bill['room_id']}: {message}")

        if success:
            count += 1

    print(f"Tổng số email gửi thành công: {count}")


if __name__ == "__main__":
    main()
