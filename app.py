

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


def calculate(bill):
    electric_usage = bill['new_electric'] - bill['old_electric']
    water_usage = bill['new_water'] - bill['old_water']
    electric_amount = electric_usage * bill['electric_price']
    water_amount = water_usage * bill['water_price']
    total = bill['rent'] + electric_amount + water_amount + bill['other_fee']
    return electric_usage, water_usage, electric_amount, water_amount, total


def money(value):
    return f'{value:,.0f}'.replace(',', '.') + ' đ'


def pdf_font():
    paths = [
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf', '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'),
    ]
    for normal, bold in paths:
        if Path(normal).is_file() and Path(bold).is_file():
            if 'TroRegular' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('TroRegular', normal))
                pdfmetrics.registerFont(TTFont('TroBold', bold))
            return 'TroRegular', 'TroBold'
    raise RuntimeError('Không tìm thấy font Unicode. Cài font DejaVu Sans hoặc Arial để xuất PDF tiếng Việt.')


def make_pdf(bill):
    regular, bold = pdf_font()
    _, _, electric_amount, water_amount, total = calculate(bill)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(210 * mm, 297 * mm),
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TroTitle', fontName=bold, fontSize=17, leading=24,
                              alignment=TA_CENTER, textColor=colors.HexColor('#17365D'), spaceAfter=10))
    styles.add(ParagraphStyle(name='TroText', fontName=regular, fontSize=10, leading=17))
    styles.add(ParagraphStyle(name='TroBoldText', parent=styles['TroText'], fontName=bold))
    styles.add(ParagraphStyle(name='TroRight', parent=styles['TroText'], alignment=TA_RIGHT))
    p = lambda s, sty='TroText': Paragraph(escape(str(s)), styles[sty])
    story = [p('HÓA ĐƠN TIỀN PHÒNG TRỌ', 'TroTitle'),
             p(f"Phòng {bill['room_id']}  |  Tháng {bill['month']:02d}/{bill['year']}", 'TroBoldText'),
             Spacer(1, 8),
             p('Người thuê: ' + (bill['tenant_name'] or 'Chưa cập nhật')),
             p('Số điện thoại: ' + (bill['phone'] or 'Chưa cập nhật')),
             Spacer(1, 14)]
    rows = [
        [p('Khoản thu', 'TroBoldText'), p('Chi tiết', 'TroBoldText'), p('Thành tiền', 'TroBoldText')],
        [p('Tiền phòng'), p('Giá thuê tháng'), p(money(bill['rent']), 'TroRight')],
        [p('Tiền điện'), p(f"{bill['old_electric']} → {bill['new_electric']} kWh × {money(bill['electric_price'])}"), p(money(electric_amount), 'TroRight')],
        [p('Tiền nước'), p(f"{bill['old_water']} → {bill['new_water']} m³ × {money(bill['water_price'])}"), p(money(water_amount), 'TroRight')],
        [p('Phí khác'), p('Wifi, vệ sinh, ...'), p(money(bill['other_fee']), 'TroRight')],
        [p('TỔNG CỘNG', 'TroBoldText'), p(''), p(money(total), 'TroBoldText')],
    ]
    table = Table(rows, colWidths=[43 * mm, 76 * mm, 51 * mm], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F0FA')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EDF5EE')),
        ('LINEBELOW', (0, 0), (-1, -1), 0.35, colors.HexColor('#C7D2DE')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
    ]))
    story.extend([table, Spacer(1, 16), p('Trạng thái: ' + bill['status'], 'TroBoldText'),
                  Spacer(1, 18), p('Hóa đơn được tạo từ phần mềm quản lý tiền phòng trọ.')])
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


try:
    init_db()
except (sqlite3.Error, OSError) as exc:
    st.error('Không thể khởi tạo cơ sở dữ liệu SQLite. Kiểm tra quyền ghi thư mục và cấu hình TRO_DB_PATH.')
    st.exception(exc)
    st.stop()
st.title('🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ_VŨ ĐỨC BÌNH')
st.sidebar.header('⚙️ Cấu hình mặc định')
gia_dien = st.sidebar.number_input('⚡ Giá điện (đ/kWh)', min_value=0, value=3500, step=100)
gia_nuoc = st.sidebar.number_input('💧 Giá nước (đ/m³)', min_value=0, value=15000, step=500)
phi_khac = st.sidebar.number_input('📦 Phí khác (đ)', min_value=0, value=150000, step=10000)
so_phong = st.sidebar.slider('Số lượng phòng', 1, 100, 10)
col_nam, col_thang = st.sidebar.columns(2)
now = datetime.now()
with col_nam:
    nam = st.selectbox('Năm', list(range(now.year - 5, now.year + 6)), index=5)
with col_thang:
    thang = st.selectbox('Tháng', list(range(1, 13)), index=now.month - 1,
                         format_func=lambda x: f'Tháng {x}')
st.sidebar.caption('Đơn giá bên trên áp dụng khi tạo hóa đơn mới; hóa đơn đã lưu giữ nguyên đơn giá cũ.')
st.header(f'📋 Nhập số liệu - Tháng {thang}/{nam}')
phong = st.selectbox('Chọn phòng cần nhập dữ liệu', range(1, so_phong + 1),
                     format_func=lambda x: f'Phòng {x}')
existing = get_bill(nam, thang, phong)
record = existing or defaults(nam, thang, phong, gia_dien, gia_nuoc, phi_khac)
if not existing:
    st.info('Phòng này chưa có hóa đơn tháng đã chọn. Nhấn Lưu để ghi vào SQLite.')

with st.form(key=f'edit_{nam}_{thang}_{phong}'):
    st.subheader(f'🏠 Cập nhật phòng {phong}')
    a, b, c = st.columns([1, 1.4, 1.2])
    with a:
        rent = st.number_input('Giá phòng (VNĐ)', min_value=0, value=int(record['rent']), step=50000)
    with b:
        tenant = st.text_input('👤 Tên người ở', value=record['tenant_name'])
    with c:
        phone = st.text_input('📞 Số điện thoại', value=record['phone'])
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        old_e = st.number_input('Số điện CŨ', min_value=0, value=int(record['old_electric']))
    with c2:
        new_e = st.number_input('Số điện MỚI', min_value=0, value=int(record['new_electric']))
    with c3:
        old_w = st.number_input('Số nước CŨ', min_value=0, value=int(record['old_water']))
    with c4:
        new_w = st.number_input('Số nước MỚI', min_value=0, value=int(record['new_water']))
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        e_price = st.number_input('Đơn giá điện', min_value=0, value=int(record['electric_price']), step=100)
    with d2:
        w_price = st.number_input('Đơn giá nước', min_value=0, value=int(record['water_price']), step=500)
    with d3:
