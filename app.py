import streamlit as st
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from io import BytesIO
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Google Auth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import gspread

# ==========================================
# THIẾT LẬP MÚI GIỜ (HANOI GMT+7)
# ==========================================
VN_TZ = timezone(timedelta(hours=7))
vntime_now = datetime.now(VN_TZ)
today_vn = vntime_now.date()

# ==========================================
# CẤU HÌNH GIAO DIỆN STREAMLIT
# ==========================================
st.set_page_config(page_title="Azura Vibe Downloader", page_icon="🚀", layout="wide")
st.title("🚀 AZURA VIBE DOWNLOADER & SHEET UPDATER")

# Sidebar cho Input
with st.sidebar:
    st.header("⚙️ Cấu Hình Chung")
    Username = st.text_input("Portal Username", value="quynh.luong")
    Password = st.text_input("Portal Password", type="password", value="Azura@2803")
    
    Ngay_bat_dau = st.date_input("📅 Ngày bắt đầu (Bắt buộc)", value=today_vn)
    
    Gioi_Han_Ket_Thuc = st.checkbox("Chọn ngày kết thúc", value=False)
    if Gioi_Han_Ket_Thuc:
        Ngay_ket_thuc = st.date_input("📅 Ngày kết thúc", value=today_vn)
    else:
        Ngay_ket_thuc = today_vn
        st.info("ℹ️ Mặc định quét đến ngày hiện tại (GMT+7).")

    Product_IDs = st.text_input("Product IDs (cách nhau dấu phẩy)", value="326, 322, 320")
    Ten_Thu_Muc_Moi = st.text_input("Tên Thư Mục Mới", value=f"{vntime_now.strftime('%d_%B').lower()}")

    st.header("🛠️ Chọn Tính Năng")
    Tao_PDF_Label = st.checkbox("Tạo PDF Label", value=True)
    Tai_Anh_Design = st.checkbox("Tải Ảnh Design lên Drive", value=False)
    Ghi_Google_Sheet = st.checkbox("Ghi dữ liệu Google Sheet", value=False)
    
    st.header("📧 Cấu Hình Email")
    Gui_Email = st.checkbox("Gửi Email Thông Báo", value=True)
    Email_Nhan_To = st.text_input("Email Nhận (TO)", value="tuongvythan.ng@gmail.com")
    Email_Nhan_CC = st.text_input("Email Nhận (CC)", value="namhoang243@gmail.com, mibi9500@gmail.com")

    run_btn = st.button("▶️ CHẠY TIẾN TRÌNH", use_container_width=True, type="primary")

# Hằng số (Cố định của dự án)
PARENT_FOLDER_ID = "1stqTuzijEkaHTQd_PCXThz_tDVDm75CX"
GOOGLE_SHEET_ID = "1WIV4otW8EvoSme7WwC9PauHc6FV8C6PxegNxt549kAk"

# Hàm làm sạch tên file
def sanitize(name):
    if not name: return "Unknown"
    return re.sub(r'[\\/*?:"<>|#]', "", str(name)).strip().replace(" ", "_")

# ==========================================
# LUỒNG XỬ LÝ CHÍNH
# ==========================================
if run_btn:
    if Ngay_ket_thuc < Ngay_bat_dau:
        st.sidebar.error("❌ Lỗi: Ngày kết thúc không được nhỏ hơn ngày bắt đầu!")
        st.stop()

    log_container = st.container()
    
    with st.status("🚀 Đang khởi chạy hệ thống...", expanded=True) as status:
        try:
            # 1. XÁC THỰC GOOGLE VỚI SERVICE ACCOUNT
            st.write("🔄 Đang xác thực Google Service Account...")
            scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            creds_dict = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            
            drive_service = build('drive', 'v3', credentials=creds)
            gc = gspread.authorize(creds) if Ghi_Google_Sheet else None
            st.write("✅ Xác thực Google thành công!")

            # Hàm tạo Drive Folder
            def create_drive_folder(folder_name, parent_id):
                file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
                folder = drive_service.files().create(body=file_metadata, fields='id').execute()
                return folder.get('id')

            # Hàm Upload File
            def upload_to_drive(local_file_path, file_name, folder_id, mime_type):
                file_metadata = {'name': file_name, 'parents': [folder_id]}
                media = MediaFileUpload(local_file_path, mimetype=mime_type, resumable=True)
                drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            st.write(f"📁 Đang tạo/chỉ định thư mục '{Ten_Thu_Muc_Moi}'...")
            TARGET_FOLDER_ID = create_drive_folder(Ten_Thu_Muc_Moi, PARENT_FOLDER_ID)
            st.write(f"✅ Đã tạo thư mục con (ID: {TARGET_FOLDER_ID})")

            # 2. LOGIN PORTAL
            st.write("🌐 Đang đăng nhập hệ thống Portal...")
            session = requests.Session()
            cookie_str = ""
            r1 = session.get("https://portal.aluffm.com/Login", timeout=15)
            token = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r1.text).group(1)
            payload = {"UserName": Username, "Password": Password, "__RequestVerificationToken": token, "RememberMe": "false"}
            session.post("https://portal.aluffm.com/Login", data=payload, headers={"Referer": "https://portal.aluffm.com/Login"}, allow_redirects=False)

            ck_dict = session.cookies.get_dict()
            if '.AspNetCore.Identity.Application' in ck_dict:
                cookie_str = "; ".join([f"{k}={v}" for k, v in ck_dict.items()])
                st.write("✅ Lấy Cookie thành công!")
            else:
                st.error("❌ Đăng nhập thất bại: Sai tài khoản hoặc mật khẩu.")
                st.stop()

            # 3. QUÉT ĐƠN HÀNG
            start_dt = datetime.combine(Ngay_bat_dau, datetime.min.time())
            end_dt = datetime.combine(Ngay_ket_thuc, datetime.max.time())
            
            str_date_range = f"{Ngay_bat_dau.strftime('%d/%m/%Y')} - {Ngay_ket_thuc.strftime('%d/%m/%Y')}"
            st.write(f"🔍 Đang quét đơn hàng từ ngày: {str_date_range}...")
            
            target_ids = [i.strip() for i in Product_IDs.split(',') if i.strip()]
            
            tong_item_vat_ly = 0
            label_urls = []
            design_queue = []
            seen_labels = set()
            page = 1

            while True:
                headers = {'Cookie': cookie_str, 'X-Requested-With': 'XMLHttpRequest'}
                res = requests.get("https://portal.aluffm.com/OnBehalfOrder/List", headers=headers, params={"pageSize": 50, "pageNumber": page}, timeout=20)
                if res.status_code != 200: break
                
                rows = res.json().get("rows", [])
                if not rows: break

                stop_page = False
                for o in rows:
                    raw_date = o.get('processAt') or o.get('createdAt') or ""
                    o_date_str = raw_date.split("T")[0] if "T" in raw_date else raw_date[:10]
                    try: o_dt = datetime.strptime(o_date_str, "%Y-%m-%d")
                    except: o_dt = None

                    if o_dt:
                        if o_dt > end_dt: continue
                        if o_dt < start_dt:
                            stop_page = True
                            break

                    items = o.get('orderProductDesigns') or []
                    l_url = o.get('partnerLabelUrl')
                    c_order = sanitize(o.get('customerOrder') or "")
                    order_qty = o.get('quantity') or 1

                    has_target = False
                    temp_designs = []
                    for idx, p in enumerate(items):
                        if str(p.get('productId')) in target_ids:
                            has_target = True
                            oid = str(p.get('orderId') or o.get('id') or "NoID")
                            p_name = sanitize(p.get('productName') or (p.get('product') or {}).get('name') or "Product")
                            product_name_idx = f"{p_name}_{idx+1}"
                            item_qty = p.get('quantity') or order_qty
                            d_url = (p.get('design') or {}).get('previewUrl') or p.get('previewUrl')
                            
                            if d_url:
                                fname = f"{oid}_{c_order}_{product_name_idx}-{item_qty}item.png"
                                temp_designs.append({"url": d_url, "fname": fname, "oid": oid, "c_order": c_order, "product_name_idx": product_name_idx, "qty": item_qty})

                    if has_target and l_url:
                        if l_url not in seen_labels:
                            seen_labels.add(l_url); label_urls.append(l_url)
                        design_queue.extend(temp_designs)

                st.write(f" └─ Đã quét xong trang {page}...")
                if stop_page: break
                page += 1

            tong_item_vat_ly = sum(item["qty"] for item in design_queue)
            st.success(f"📊 Tìm thấy: {len(label_urls)} Labels | {len(design_queue)} Designs | Tổng Item: {tong_item_vat_ly}")

            # 4. XỬ LÝ FILE PDF & DRIVE
            if Tao_PDF_Label and label_urls:
                st.write("📦 Đang xử lý gộp file PDF Labels...")
                imgs = []
                for u in label_urls:
                    try:
                        r = requests.get(u, timeout=15)
                        if r.status_code == 200: imgs.append(Image.open(BytesIO(r.content)).convert('RGB'))
                    except: pass

                if imgs:
                    pdf_filename = f"Labels_{vntime_now.strftime('%d%m_%H%M')}.pdf"
                    imgs[0].save(pdf_filename, "PDF", save_all=True, append_images=imgs[1:])
                    upload_to_drive(pdf_filename, pdf_filename, TARGET_FOLDER_ID, 'application/pdf')
                    os.remove(pdf_filename)
                    st.write("✅ Đã tải PDF lên Drive thành công!")
            elif Tao_PDF_Label and not label_urls:
                st.warning("⚠️ Không tìm thấy Label nào trong khoảng thời gian này.")

            # 5. XỬ LÝ DESIGN & SHEET
            sheet_rows_to_append = []
            if design_queue:
                count = 0
                for item in design_queue:
                    f_name = item["fname"]
                    upload_success = False

                    if Tai_Anh_Design:
                        try:
                            r = requests.get(item["url"], stream=True, timeout=25)
                            if r.status_code == 200:
                                with open(f_name, 'wb') as out_f:
                                    for chunk in r.iter_content(8192): out_f.write(chunk)
                                upload_to_drive(f_name, f_name, TARGET_FOLDER_ID, 'image/png')
                                os.remove(f_name)
                                count += 1
                                upload_success = True
                        except Exception as e:
                            st.error(f"❌ Lỗi tải ảnh {f_name}: {e}")
                    else:
                        upload_success = True

                    if Ghi_Google_Sheet and upload_success:
                        portal_link = f"https://portal.aluffm.com/OnBehalfOrder?searchText={item['c_order']}"
                        sheet_rows_to_append.append([Ten_Thu_Muc_Moi, item["oid"], item["c_order"], item["url"], item["product_name_idx"], item["qty"], portal_link])

                if Tai_Anh_Design:
                    st.write(f"🎉 Đã tải lên Drive: {count}/{len(design_queue)} Designs.")

            # Biến lưu trữ vị trí dòng để gửi Email
            start_row = 0
            end_row = 0
            
            if Ghi_Google_Sheet and sheet_rows_to_append:
                st.write("📝 Đang ghi dữ liệu vào Google Sheet...")
                try:
                    sh = gc.open_by_key(GOOGLE_SHEET_ID)
                    worksheet = sh.get_worksheet(0)
                    
                    # Đếm số dòng hiện tại (dựa vào cột A)
                    current_rows = len(worksheet.col_values(1))
                    start_row = current_rows + 1
                    end_row = start_row + len(sheet_rows_to_append) - 1
                    
                    worksheet.append_rows(sheet_rows_to_append)
                    st.write(f"✅ Đã ghi dữ liệu Sheet thành công (Từ dòng {start_row} đến {end_row})!")
                except Exception as e:
                    st.error(f"❌ Lỗi khi ghi Google Sheet: {e}")

            # 6. GỬI EMAIL
            if Gui_Email:
                st.write("📧 Đang gửi email báo cáo...")
                Email_Nguoi_Gui = st.secrets["email_config"]["sender_email"]
                Mat_Khau_Ung_Dung = st.secrets["email_config"]["app_password"]
                
                drive_link = f"https://drive.google.com/drive/folders/{TARGET_FOLDER_ID}" if TARGET_FOLDER_ID else "Không có link"
                sheet_link = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit"
                
                # Báo cáo Sheet (Chỉ hiển thị nếu có ghi)
                sheet_report_html = ""
                if Ghi_Google_Sheet and start_row > 0:
                    sheet_report_html = f"""
                    <h3 style="border-bottom: 1px solid #ccc; padding-bottom: 5px;">📗 Cập nhật Google Sheet:</h3>
                    <ul>
                        <li><b>Dữ liệu mới:</b> Đã ghi từ dòng <b style="color: #E67E22;">{start_row}</b> đến dòng <b style="color: #E67E22;">{end_row}</b></li>
                        <li>👉 <b>Mở File Quản Lý:</b> <a href="{sheet_link}" style="color: #27AE60; font-weight: bold;">Truy cập Google Sheet tại đây</a></li>
                    </ul>
                    """
                
                html_content = f"""
                <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <h2 style="color: #2E86C1;">🚀 BÁO CÁO TỰ ĐỘNG AZURA</h2>
                    <p>Đã chạy tiến trình lấy dữ liệu trong khoảng thời gian:</p>
                    <p>⏳ <b>Từ {Ngay_bat_dau.strftime('%d/%m/%Y')} đến {Ngay_ket_thuc.strftime('%d/%m/%Y')}</b>.</p>
                    
                    <h3 style="border-bottom: 1px solid #ccc; padding-bottom: 5px;">📊 Thông số sản xuất:</h3>
                    <ul>
                        <li><b>Số lượng Đơn (Labels):</b> {len(label_urls)}</li>
                        <li><b>Số lượng File Design:</b> {len(design_queue)}</li>
                        <li><b style="color: #C0392B;">Tổng Item cần sản xuất:</b> {tong_item_vat_ly}</li>
                    </ul>
                    <p>👉 <b>Link Folder Drive lưu trữ:</b> <a href="{drive_link}" style="color: #2980B9; font-weight: bold;">{Ten_Thu_Muc_Moi}</a></p>
                    
                    {sheet_report_html}
                    
                    <hr>
                    <p style="font-size: 11px; color: gray;">Email tự động tạo bởi VibeCoder Assistant lúc {vntime_now.strftime('%H:%M:%S %d/%m/%Y')}.</p>
                </body></html>
                """
                msg = MIMEMultipart()
                msg['From'] = Email_Nguoi_Gui
                msg['To'] = Email_Nhan_To
                if Email_Nhan_CC.strip(): msg['Cc'] = Email_Nhan_CC
                msg['Subject'] = f"[Azura Production] Batch {str_date_range} - Thư mục: {Ten_Thu_Muc_Moi}"
                msg.attach(MIMEText(html_content, 'html'))

                try:
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(Email_Nguoi_Gui, Mat_Khau_Ung_Dung.replace(" ", ""))
                    
                    all_recipients = [e.strip() for e in Email_Nhan_To.split(',') if e.strip()] + [e.strip() for e in Email_Nhan_CC.split(',') if e.strip()]
                    if all_recipients:
                        server.sendmail(Email_Nguoi_Gui, all_recipients, msg.as_string())
                    server.quit()
                    st.write("✅ Đã gửi Email thành công!")
                except Exception as e:
                    st.error(f"❌ Lỗi khi gửi Email: {e}")

            status.update(label="🎉 HOÀN TẤT QUY TRÌNH!", state="complete", expanded=False)
            st.balloons()

        except Exception as e:
            status.update(label="❌ Có lỗi xảy ra!", state="error", expanded=True)
            st.error(str(e))
