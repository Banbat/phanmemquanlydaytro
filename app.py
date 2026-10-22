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
        other = st.number_input('Phí khác', min_value=0, value=int(record['other_fee']), step=10000)
    with d4:
        status = st.selectbox('💳 Trạng thái thanh toán', STATUS,
                              index=STATUS.index(record['status']) if record['status'] in STATUS else 0)
    submitted = st.form_submit_button('💾 Lưu dữ liệu phòng', type='primary')
    if submitted:
        if new_e < old_e or new_w < old_w:
            st.error('Số điện/nước MỚI không được nhỏ hơn số CŨ. Vui lòng kiểm tra.')
        else:
            updated = dict(year=nam, month=thang, room_id=phong,
                           tenant_name=tenant.strip(), phone=phone.strip(), rent=rent,
                           old_electric=old_e, new_electric=new_e,
                           old_water=old_w, new_water=new_w,
                           electric_price=e_price, water_price=w_price,
                           other_fee=other, status=status)
            save_bill(updated)
            st.success('Đã lưu dữ liệu vào SQLite!')
            st.rerun()

if existing:
    _, _, _, _, current_total = calculate(existing)
    st.metric('💰 Tổng hóa đơn phòng đang chọn', money(current_total))
    try:
        pdf_bytes = make_pdf(existing)
        st.download_button('📄 Xuất PDF phòng này', data=pdf_bytes,
                           file_name=f'Hoa_don_phong_{phong}_{thang:02d}_{nam}.pdf',
                           mime='application/pdf')
    except RuntimeError as exc:
        st.error(str(exc))

st.divider()
st.header(f'📊 Bảng tổng hợp - Tháng {thang}/{nam}')
with connect() as conn:
    saved = [dict(r) for r in conn.execute('''SELECT * FROM bills WHERE year=? AND month=? AND room_id<=?
                                              ORDER BY room_id''', (nam, thang, so_phong))]
rows = []
for bill in saved:
    _, _, tien_dien, tien_nuoc, total = calculate(bill)
    rows.append({'Phòng': f"Phòng {bill['room_id']}", 'Người ở': bill['tenant_name'],
                 'Số điện thoại': bill['phone'], 'Giá phòng': bill['rent'],
                 'Số điện cũ': bill['old_electric'], 'Số điện mới': bill['new_electric'],
                 'Tiền điện': tien_dien, 'Số nước cũ': bill['old_water'],
                 'Số nước mới': bill['new_water'], 'Tiền nước': tien_nuoc,
                 'Phí khác': bill['other_fee'], 'Tổng tiền': total,
                 'Trạng thái': bill['status']})
if rows:
    df = pd.DataFrame(rows)
    monetary_cols = ['Giá phòng', 'Tiền điện', 'Tiền nước', 'Phí khác', 'Tổng tiền']
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format='%d') for c in monetary_cols})
    paid = sum(row['Tổng tiền'] for row in rows if row['Trạng thái'] == STATUS[1])
    unpaid = sum(row['Tổng tiền'] for row in rows if row['Trạng thái'] == STATUS[0])
    m1, m2, m3 = st.columns(3)
    m1.metric('Tổng phải thu', money(paid + unpaid))
    m2.metric('Đã thu', money(paid))
    m3.metric('Chưa thu', money(unpaid))
    st.download_button('📥 Xuất báo cáo CSV', data=df.to_csv(index=False).encode('utf-8-sig'),
                       file_name=f'Bang_Tien_Phong_{thang:02d}_{nam}.csv', mime='text/csv')
else:
    st.info('Chưa có hóa đơn nào được lưu trong tháng này.')
st.caption(f'Cơ sở dữ liệu SQLite: {DB_PATH}. Hãy sao lưu file này định kỳ.')
