import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import subprocess
import sys

class Douyin2TikTokGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 Douyin2TikTok - Bảng Điều Khiển")
        self.root.geometry("820x620")
        
        # Frame input
        input_frame = ttk.LabelFrame(root, text="URL Douyin / File Video", padding=(10, 5))
        input_frame.pack(fill="x", padx=10, pady=5)
        
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(input_frame, textvariable=self.url_var, width=80)
        self.url_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Frame Options
        options_frame = ttk.LabelFrame(root, text="Cấu Hình", padding=(10, 5))
        options_frame.pack(fill="x", padx=10, pady=5)
        
        self.voice_var = tk.StringVar(value="male")
        ttk.Label(options_frame, text="Giọng đọc:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        voice_cb = ttk.Combobox(options_frame, textvariable=self.voice_var, values=["male", "female"], state="readonly", width=15)
        voice_cb.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        self.mode_var = tk.StringVar(value="tts_with_bgm")
        ttk.Label(options_frame, text="Chế độ:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        mode_cb = ttk.Combobox(options_frame, textvariable=self.mode_var, values=["tts_with_bgm", "subtitle_only"], state="readonly", width=15)
        mode_cb.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        self.fast_var = tk.BooleanVar(value=False)
        fast_check = ttk.Checkbutton(options_frame, text="Render siêu tốc (--no-sub)", variable=self.fast_var)
        fast_check.grid(row=0, column=4, padx=15, pady=5)
        
        # Action Buttons
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        self.start_btn = ttk.Button(btn_frame, text="▶️ Bắt Đầu Render", command=self.start_render)
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹️ Dừng Lại", command=self.stop_render, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        # Log Output
        log_frame = ttk.LabelFrame(root, text="Tiến Độ / Log", padding=(10, 5))
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg="black", fg="#00ff00", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)
        
        self.process = None

    def log(self, message):
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)

    def start_render(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập URL Douyin!")
            return
            
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log("🚀 Bắt đầu khởi chạy pipeline...\n")
        
        cmd = [
            sys.executable, "-u", "main.py", url,
            "--voice", self.voice_var.get(),
            "--mode", self.mode_var.get()
        ]
        
        if self.fast_var.get():
            cmd.append("--no-sub")

        self.thread = threading.Thread(target=self.run_process, args=(cmd,))
        self.thread.daemon = True
        self.thread.start()

    def run_process(self, cmd):
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd="D:/Antigravity/TIKTOK"
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.root.after(0, self.log, line)
                    
            self.process.wait()
            
            if self.process.returncode == 0:
                self.root.after(0, self.log, "\n✅ HOÀN TẤT RENDER THÀNH CÔNG!\n")
            else:
                self.root.after(0, self.log, f"\n❌ Render kết thúc với mã lỗi {self.process.returncode}\n")
                
        except Exception as e:
            self.root.after(0, self.log, f"\n❌ Lỗi hệ thống: {e}\n")
        finally:
            self.root.after(0, self.reset_ui)

    def stop_render(self):
        if self.process:
            self.process.terminate()
            self.log("\n⚠️ ĐÃ HỦY TIẾN TRÌNH RENDER.\n")
            
    def reset_ui(self):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.process = None

if __name__ == "__main__":
    root = tk.Tk()
    app = Douyin2TikTokGUI(root)
    root.mainloop()
