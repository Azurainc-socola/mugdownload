import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import requests
from PIL import Image
from io import BytesIO
import threading
import re
from datetime import datetime
import os

class AzuraVibeDownloaderV20:
    def __init__(self, root):
        self.root = root
        self.root.title("Azura Vibe - V20 (Real ProductName & Detailed Log)")
        self.root.geometry("750x900")

        # --- 1. Login ---
        login_frame = tk.LabelFrame(root, text=" 1. Login & Cookie ", font=("Arial", 10, "bold"), fg="#D32F2F")
        login_frame.pack(fill="x", padx=10, pady=5, ipady=5)
        self.entry_user = tk.Entry(login_frame, width=15); self.entry_user.insert(0, "quynh.luong")
        self.entry_pass = tk.Entry(login_frame, width=15, show="*")
        tk.Label(login_frame, text="U:").grid(row=0, column=0); self.entry_user.grid(row=0, column=1)
        tk.Label(login_frame, text="P:").grid(row=0, column=2); self.entry_pass.grid(row=0, column=3)
        tk.Button(login_frame, text="Lấy Cookie", command=self.thread_get_cookie, bg="#FF9800").grid(row=0, column=4, padx=10)
        self.entry_cookie = tk.Text(root, height=2); self.entry_cookie.pack(fill="x", padx=10)

        # --- 2. Filter Config ---
        filter_frame = tk.LabelFrame(root, text=" 2. Bộ lọc (Ngày & SP) ", font=("Arial", 10, "bold"))
        filter_frame.pack(fill="x", padx=10, pady=5, ipady=5)
        
        tk.Label(filter_frame, text="Từ ngày (YYYY-MM-DD):").grid(row=0, column=0)
        self.date_start = tk.Entry(filter_frame, width=12); self.date_start.grid(row=0, column=1)
        self.date_start.insert(0, datetime.now().strftime("%Y-%m-%d"))

        tk.Label(filter_frame, text="Product IDs:").grid(row=1, column=0)
        self.entry_ids = tk.Entry(filter_frame); self.entry_ids.grid(row=1, column=1, sticky="we", columnspan=2)
        self.entry_ids.insert(0, "286, 326, 320")

        # --- 3. Output ---
        tk.Label(root, text="3. Thư mục lưu Design:").pack(anchor="w", padx=10)
        out_f = tk.Frame(root); out_f.pack(fill="x", padx=10)
        self.entry_out = tk.Entry(out_f); self.entry_out.pack(side="left", fill="x", expand=True)
        tk.Button(out_f, text="Chọn", command=self.browse_out).pack(side="right")

        # --- 4. Run ---
        self.btn_run = tk.Button(root, text="CHẠY: TẢI LABEL & DESIGN", bg="#E91E63", fg="white", font=("Arial", 12, "bold"), command=self.start_main_process)
        self.btn_run.pack(fill="x", padx=10, pady=10, ipady=10)

        self.log_text = scrolledtext.ScrolledText(root, height=18, state='disabled', bg="#f0f0f0")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

    def sanitize(self, name):
        if not name: return "Unknown"
        return re.sub(r'[\\/*?:"<>|#]', "", str(name)).strip().replace(" ", "_")

    def browse_out(self):
        f = filedialog.askdirectory()
        if f: self.entry_out.delete(0, tk.END); self.entry_out.insert(0, f)

    def log(self, msg):
        def update():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see(tk.END); self.log_text.config(state='disabled')
        self.root.after(0, update)

    def thread_get_cookie(self):
        threading.Thread(target=self.auto_fetch_cookie, daemon=True).start()

    def auto_fetch_cookie(self):
        u, p = self.entry_user.get().strip(), self.entry_pass.get().strip()
        try:
            s = requests.Session()
            r = s.get("https://portal.aluffm.com/Login")
            token = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text).group(1)
            payload = {"UserName": u, "Password": p, "__RequestVerificationToken": token, "RememberMe": "false"}
            s.post("https://portal.aluffm.com/Login", data=payload, headers={"Referer": "https://portal.aluffm.com/Login"}, allow_redirects=False)
            ck_dict = s.cookies.get_dict()
            if '.AspNetCore.Identity.Application' in ck_dict:
                ck = "; ".join([f"{k}={v}" for k, v in ck_dict.items()])
                self.root.after(0, lambda: (self.entry_cookie.delete("1.0", tk.END), self.entry_cookie.insert(tk.END, ck)))
                self.log("Lấy Cookie mới thành công.")
            else: self.log("Lỗi: Sai user/pass.")
        except: self.log("Lỗi hệ thống khi Login.")

    def start_main_process(self):
        threading.Thread(target=self.main_pipeline, daemon=True).start()

    def main_pipeline(self):
        out_dir = self.entry_out.get().strip()
        cookie = self.entry_cookie.get("1.0", tk.END).strip()
        target_ids = [i.strip() for i in self.entry_ids.get().split(',') if i.strip()]
        
        try: start_dt = datetime.strptime(self.date_start.get().strip(), "%Y-%m-%d")
        except: self.log("Lỗi: Ngày bắt đầu sai định dạng (YYYY-MM-DD)"); return

        if not out_dir or not cookie: self.log("Lỗi: Thiếu Folder lưu hoặc Cookie!"); return

        self.log("--- BẮT ĐẦU QUÉT ĐƠN ---")
        design_queue, label_urls, seen_labels = [], [], set()
        page = 1

        try:
            while True:
                res = requests.get("https://portal.aluffm.com/OnBehalfOrder/List", 
                                 headers={'Cookie': cookie, 'X-Requested-With': 'XMLHttpRequest'}, 
                                 params={"pageSize": 50, "pageNumber": page}, timeout=20)
                if res.status_code != 200: break
                
                try: rows = res.json().get("rows", [])
                except: break
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
                    c_order = self.sanitize(o.get('customerOrder') or "")
                    
                    has_target = False
                    temp_designs = []
                    for idx, p in enumerate(items):
                        if str(p.get('productId')) in target_ids:
                            has_target = True
                            oid = str(p.get('orderId') or o.get('id') or "NoID")
                            
                            # CẬP NHẬT QUAN TRỌNG: Quét sâu để lấy tên sản phẩm
                            raw_p_name = p.get('productName') or (p.get('product') or {}).get('name') or "Product"
                            p_name = self.sanitize(raw_p_name)
                            
                            d_url = (p.get('design') or {}).get('previewUrl') or p.get('previewUrl')
                            
                            if d_url:
                                fname = f"{oid}_{c_order}_{p_name}_{idx+1}.png"
                                temp_designs.append((d_url, fname))

                    if has_target and l_url:
                        if l_url not in seen_labels:
                            seen_labels.add(l_url); label_urls.append(l_url)
                        design_queue.extend(temp_designs)

                self.log(f"Đã quét trang {page}...")
                if stop_page: break
                page += 1

            self.log(f"Tổng hợp: Cần tải {len(label_urls)} Label & {len(design_queue)} Design.")
            if label_urls: self.download_pdf_labels(label_urls)
            if design_queue: self.download_designs(design_queue, out_dir)

        except Exception as e: self.log(f"Lỗi hệ thống: {e}")
        self.log("--- HOÀN TẤT QUY TRÌNH ---")

    def download_pdf_labels(self, urls):
        self.log("Đang gộp file PDF nhãn...")
        imgs = []
        for u in urls:
            try:
                r = requests.get(u, timeout=15)
                if r.status_code == 200: imgs.append(Image.open(BytesIO(r.content)).convert('RGB'))
            except: pass
        if imgs:
            path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"Labels_{datetime.now().strftime('%H%M')}.pdf")
            if path: imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:])
            self.log("✅ Lưu PDF Label thành công.")

    def download_designs(self, queue, out_dir):
        if not os.path.exists(out_dir): os.makedirs(out_dir, exist_ok=True)
        count = 0
        self.log(f"Bắt đầu tải {len(queue)} Design...")
        for u, f in queue:
            try:
                r = requests.get(u, stream=True, timeout=25)
                if r.status_code == 200:
                    with open(os.path.join(out_dir, f), 'wb') as out:
                        for chunk in r.iter_content(8192): out.write(chunk)
                    count += 1
                    # CẬP NHẬT LOG: Hiển thị tên file vừa tải
                    self.log(f" └─ Đã lưu: {f}")
                else:
                    self.log(f" └─ [Lỗi HTTP {r.status_code}] Không thể tải: {f}")
            except Exception as e: 
                self.log(f" └─ [Lỗi] {f} : {e}")
        self.log(f"✅ Hoàn tất tải {count}/{len(queue)} Design.")

if __name__ == "__main__":
    root = tk.Tk(); app = AzuraVibeDownloaderV20(root); root.mainloop()
