"""Script tiện ích giúp người dùng cài đặt Gemini API Key miễn phí."""
import sys
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import AI_KEY_FILE
from pipeline.translator import get_active_gemini_key, translate_single

def main():
    print("=" * 65)
    print("   🤖 CÀI ĐẶT GOOGLE GEMINI AI KEY (DỊCH THUẬT SIÊU MƯỢT)")
    print("=" * 65)
    
    current_key = get_active_gemini_key()
    if current_key:
        masked = current_key[:6] + "..." + current_key[-4:]
        print(f"\n[INFO] Đã tìm thấy Gemini API Key đang hoạt động: {masked}")
    else:
        print("\n[INFO] Hiện tại đang dùng bộ dịch nâng cao (Chưa có Gemini AI Key).")
        
    print("\n--- HƯỚNG DẪN LẤY GEMINI API KEY HOÀN TOÀN MIỄN PHÍ ---")
    print("1. Truy cập vào trang web: https://aistudio.google.com/app/apikey")
    print("2. Đăng nhập tài khoản Google của bạn và bấm 'Create API key' (Tạo khóa API).")
    print("3. Bấm Copy khóa API (chuỗi ký tự bắt đầu bằng 'AIzaSy...').")
    print("4. Dán (Paste) khóa API vào bên dưới:")
    print("-" * 65)
    
    try:
        key_input = input("👉 Dán Gemini API Key vào đây (hoặc nhấn Enter để bỏ qua): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nĐã hủy.")
        return
        
    if not key_input:
        if current_key:
            print("Giữ nguyên khóa API hiện tại.")
        else:
            print("Chưa nhập khóa. Hệ thống sẽ tiếp tục dùng bộ dịch Enhanced Translator.")
        return
        
    AI_KEY_FILE.write_text(key_input, encoding='utf-8')
    print(f"\n✅ ĐÃ LƯU THÀNH CÔNG KHÓA GEMINI AI VÀO: {AI_KEY_FILE}")
    
    # Test key
    print("\n🧪 Đang kiểm tra thử nghiệm bản dịch với Gemini AI...")
    try:
        test_vi = translate_single("妹妹你看这个烤得很厉害，太香了！")
        print(f"  zh: 妹妹你看这个烤得很厉害，太香了！")
        print(f"  vi: {test_vi}")
        print("\n🎉 CHÚC MỪNG! Gemini AI đã hoạt động xuất sắc! Từ nay các video sẽ được dịch cực mượt!")
    except Exception as e:
        print(f"⚠️ Cảnh báo khi test key: {e}")

if __name__ == "__main__":
    main()
