"""Script tiện ích giúp người dùng cài đặt cookie Douyin nhanh chóng."""
import sys
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import COOKIE_FILE
from utils.cookie_helper import get_douyin_cookies, parse_cookie_string

def main():
    print("=" * 60)
    print("   🔑 CÀI ĐẶT COOKIE TÀI KHOẢN DOUYIN CHO DỰ ÁN")
    print("=" * 60)
    
    current = get_douyin_cookies()
    if current:
        print(f"\n[INFO] Đã tìm thấy {len(current)} cookies hiện có trong hệ thống.")
        for k in list(current.keys())[:5]:
            print(f"  • {k}: {current[k][:20]}...")
        if len(current) > 5:
            print(f"  ... và {len(current) - 5} cookies khác.")
    else:
        print("\n[INFO] Hiện tại chưa có cookie tài khoản Douyin nào.")
        
    print("\n--- HƯỚNG DẪN LẤY COOKIE TỪ TRÌNH DUYỆT (CHROME / EDGE) ---")
    print("1. Mở trang https://www.douyin.com trên trình duyệt và ĐĂNG NHẬP nick Douyin của bạn.")
    print("2. Nhấn phím F12 -> chọn tab 'Console' -> dán dòng lệnh sau rồi bấm Enter:")
    print("      copy(document.cookie)")
    print("3. Dán (Paste) chuỗi cookie vừa copy vào bên dưới:")
    print("-" * 60)
    
    try:
        cookie_str = input("👉 Dán chuỗi cookie vào đây (rồi nhấn Enter): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nĐã hủy.")
        return
        
    if not cookie_str:
        print("❌ Chuỗi cookie trống. Không có gì được lưu.")
        return
        
    parsed = parse_cookie_string(cookie_str)
    if not parsed:
        print("❌ Không thể phân tích chuỗi cookie. Vui lòng kiểm tra lại định dạng.")
        return
        
    COOKIE_FILE.write_text(cookie_str, encoding='utf-8')
    print(f"\n✅ ĐÃ LƯU THÀNH CÔNG {len(parsed)} COOKIES VÀO:")
    print(f"   📁 {COOKIE_FILE}")
    print("\nBây giờ bạn có thể tải mọi video Douyin chất lượng cao nhất không bị chặn!")

if __name__ == "__main__":
    main()
