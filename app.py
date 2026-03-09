import streamlit as st
import requests
import re
from PIL import Image
from io import BytesIO
from datetime import datetime
import os
import zipfile
import tempfile

# --- Setup UI ---
st.set_page_config(page_title="Azura Vibe Downloader Web", layout="centered")
st.title("🚀 Azura Vibe Downloader (Web Version)")

# Quản lý Cookie bằng Session State để không bị mất khi load lại trang
if "cookie" not in st.session_state:
    st.session_state.cookie = ""

def sanitize(name):
    """Làm sạch tên file để tránh lỗi hệ điều hành"""
    if not name: return "Unknown"
    return re.sub(r'[\\/*?:"<>|#]', "", str(name)).strip().replace(" ", "_")

# --- UI Components ---
with st.expander("🔑 1. Đăng nhập hệ thống", expanded=True):
    col1, col2 = st.columns(2)
    user = col1.text_input("Username", value="quynh.luong")
    pwd = col2.text_input("Password", type="password")
    
    if st.button("LẤY COOKIE"):
        with st.spinner("Đang kết nối đến hệ thống..."):
            try:
                s = requests.Session()
                r = s.get("https://portal.aluffm.com/Login", timeout=15)
                token = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text).group(1)
                
                payload = {"UserName": user, "Password": pwd, "__RequestVerificationToken": token, "RememberMe": "false"}
                s.post("https://portal.aluffm.com/Login", data=payload, headers={"Referer": "https://portal.aluffm.com/Login"}, allow_redirects=False)
                
                ck_dict = s.cookies.get_dict()
                if '.AspNetCore.Identity.Application' in ck_dict:
                    st.session_state.cookie = "; ".join([f"{k}={v}" for k, v in ck_dict.items()])
                    st.success("✅ Login thành công! Đã lấy Cookie.")
                else:
                    st.error("❌ Login thất bại: Sai tài khoản hoặc mật khẩu.")
            except Exception as e:
                st.error(f"Lỗi kết nối: {e}")

if st.session_state.cookie:
    st.info("🟢 Trạng thái: Cookie đã sẵn sàng!")
else:
    st.warning("🔴 Trạng thái: Chưa có Cookie. Vui lòng đăng nhập.")

with st.expander("⚙️ 2. Cấu hình quét", expanded=True):
    date_start = st.text_input("Từ ngày (YYYY-MM-DD)", value=datetime.now().strftime("%Y-%m-%d"))
    target_ids_input = st.text_input("Product IDs (ngăn cách bằng dấu phẩy)", value="286, 326, 320")

# --- Main Pipeline ---
if st.button("🚀 CHẠY QUY TRÌNH QUÉT & TẢI", type="primary"):
    if not st.session_state.cookie:
        st.error("⚠️ Vui lòng LẤY COOKIE ở bước 1 trước khi chạy!")
        st.stop()
        
    try:
        start_dt = datetime.strptime(date_start.strip(), "%Y-%m-%d")
    except:
        st.error("⚠️ Ngày bắt đầu sai định dạng (YYYY-MM-DD)")
        st.stop()
        
    target_ids = [i.strip() for i in target_ids_input.split(',') if i.strip()]
    
    # Khu vực in Log realtime
    st.write("📝 **System Logs:**")
    log_area = st.empty()
    logs = []
    
    def add_log(msg):
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        log_area.code("\n".join(logs), language="text")

    add_log("--- BẮT ĐẦU QUY TRÌNH QUÉT ĐƠN ---")
    
    # Tạo thư mục tạm trên Server
    with tempfile.TemporaryDirectory() as temp_dir:
        design_queue, label_urls, seen_labels = [], [], set()
        page = 1
        
        try:
            # 1. FETCH API & BINDING
            while True:
                res = requests.get("https://portal.aluffm.com/OnBehalfOrder/List", 
                                 headers={'Cookie': st.session_state.cookie, 'X-Requested-With': 'XMLHttpRequest'}, 
                                 params={"pageSize": 50, "pageNumber": page}, timeout=20)
                if res.status_code != 200: 
                    add_log(f"Lỗi HTTP {res.status_code}")
                    break
                
                try: rows = res.json().get("rows", [])
                except: 
                    add_log("Lỗi: API không trả về JSON hợp lệ.")
                    break
                    
                if not rows: break

                stop_page = False
                for o in rows:
                    raw_date = o.get('processAt') or o.get('createdAt') or ""
                    o_date_str = raw_date.split("T")[0] if "T" in raw_date else raw_date[:10]
                    try: o_dt = datetime.strptime(o_date_str, "%Y-%m-%d")
                    except: o_dt = None

                    if o_dt and o_dt < start_dt:
                        stop_page = True; break

                    items = o.get('orderProductDesigns') or []
                    l_url = o.get('partnerLabelUrl')
                    c_order = sanitize(o.get('customerOrder') or "")
                    
                    has_target = False
                    temp_designs = []
                    for idx, p in enumerate(items):
                        if str(p.get('productId')) in target_ids:
                            has_target = True
                            oid = str(p.get('orderId') or o.get('id') or "NoID")
                            raw_p_name = p.get('productName') or (p.get('product') or {}).get('name') or "Product"
                            p_name = sanitize(raw_p_name)
                            
                            d_url = (p.get('design') or {}).get('previewUrl') or p.get('previewUrl')
                            
                            if d_url:
                                fname = f"{oid}_{c_order}_{p_name}_{idx+1}.png"
                                temp_designs.append((d_url, fname))

                    if has_target and l_url:
                        if l_url not in seen_labels:
                            seen_labels.add(l_url); label_urls.append(l_url)
                        design_queue.extend(temp_designs)

                add_log(f"Đã quét trang {page}...")
                if stop_page: break
                page += 1

            add_log(f"Tổng hợp: Cần tải {len(label_urls)} Label & {len(design_queue)} Design.")
            
            # 2. DOWNLOAD LABELS
            if label_urls:
                add_log("Đang gộp file PDF nhãn...")
                imgs = []
                for u in label_urls:
                    try:
                        r = requests.get(u, timeout=15)
                        if r.status_code == 200: imgs.append(Image.open(BytesIO(r.content)).convert('RGB'))
                    except: pass
                if imgs:
                    pdf_path = os.path.join(temp_dir, f"Labels_{datetime.now().strftime('%H%M')}.pdf")
                    imgs[0].save(pdf_path, "PDF", save_all=True, append_images=imgs[1:])
                    add_log(f"✅ Đã lưu PDF: {os.path.basename(pdf_path)}")

            # 3. DOWNLOAD DESIGNS
            if design_queue:
                add_log(f"Bắt đầu tải {len(design_queue)} Design...")
                count = 0
                for u, f in design_queue:
                    try:
                        r = requests.get(u, stream=True, timeout=25)
                        if r.status_code == 200:
                            with open(os.path.join(temp_dir, f), 'wb') as out:
                                for chunk in r.iter_content(8192): out.write(chunk)
                            count += 1
                            add_log(f" └─ Đã lưu: {f}")
                    except Exception as e:
                        add_log(f" └─ Lỗi tải {f}: {e}")
                add_log(f"✅ Hoàn tất tải {count}/{len(design_queue)} Design.")

            # 4. TẠO FILE ZIP ĐỂ DOWNLOAD
            if len(os.listdir(temp_dir)) > 0:
                add_log("Đang nén file ZIP...")
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zip_file.write(file_path, arcname=file)
                add_log("🎉 HOÀN TẤT TOÀN BỘ QUY TRÌNH!")
                
                st.success("Tải dữ liệu thành công! Vui lòng bấm nút bên dưới để tải file ZIP về máy.")
                st.download_button(
                    label="📥 TẢI XUỐNG KẾT QUẢ (.ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name=f"Azura_Designs_{datetime.now().strftime('%m%d_%H%M')}.zip",
                    mime="application/zip",
                    type="primary"
                )
            else:
                add_log("Không có file nào được tải xuống.")
                st.warning("Không tìm thấy dữ liệu phù hợp với bộ lọc.")

        except Exception as e:
            add_log(f"Lỗi hệ thống: {e}")
            st.error("Quy trình bị lỗi, vui lòng kiểm tra Log.")
