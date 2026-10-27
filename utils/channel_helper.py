"""Channel & Author folder management utilities (Vietnamese Naming + Profile Cache)."""
import re
import json
import logging
from pathlib import Path
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

# ─── Profile cache file ───────────────────────────────────────────────────────
CHANNEL_PROFILE_PATH = Path("D:/Antigravity/TIKTOK/cache/channel_profiles.json")

# ─── Bảng tên kênh Tiếng Việt ─────────────────────────────────────────────────
KNOWN_CHANNELS_VN = {
    "甘二娃": "Kênh Nhị Oa",
    "二娃": "Kênh Nhị Oa",
    "erwa": "Kênh Nhị Oa",
    "宝妈凉皮（两元）": "Kênh Lương Bì Mẹ Bỉm",
    "宝妈凉皮": "Kênh Lương Bì Mẹ Bỉm",
    "梦梦摆摊日记": "Kênh Mì Lạnh Xe Đẩy - Mộng Mộng",
    "刘冰冰": "Kênh Tiệm Tạp Hóa - Lưu Băng Băng",
    "平凡的胡德禄": "Kênh Mèo Hài Hước - Hồ Đức Lộc",
    "佳减乘除": "Kênh Ẩm Thực Văn Phòng - Gia Gia",
    "我家家呀": "Kênh Ẩm Thực Văn Phòng - Gia Gia",
    "桃气小竹": "Kênh Ăn Vặt Tàu Cao Tốc - Tiểu Trúc",
}

# ─── Bảng giọng đọc mặc định theo kênh (dựa trên giới tính nhân vật chính) ───
CHANNEL_VOICE_MAP = {
    "Kênh Nhị Oa":                        "vi-VN-NamMinhNeural",   # Nam chính
    "Kênh Lương Bì Mẹ Bỉm":              "vi-VN-HoaiMyNeural",    # Mẹ bỉm - nữ
    "Kênh Mì Lạnh Xe Đẩy - Mộng Mộng":  "vi-VN-HoaiMyNeural",    # Nữ bán hàng
    "Kênh Tiệm Tạp Hóa - Lưu Băng Băng": "vi-VN-HoaiMyNeural",   # Nữ chủ tiệm
    "Kênh Mèo Hài Hước - Hồ Đức Lộc":   "vi-VN-HoaiMyNeural",    # Nữ chính dễ thương
    "Kênh Ẩm Thực Văn Phòng - Gia Gia":  "vi-VN-NamMinhNeural",   # Nam/đa giọng
    "Kênh Ăn Vặt Tàu Cao Tốc - Tiểu Trúc": "vi-VN-HoaiMyNeural", # Nữ
}

# ─── Profile Cache API ────────────────────────────────────────────────────────

def _load_profiles() -> dict:
    """Đọc toàn bộ profile cache từ file JSON."""
    try:
        if CHANNEL_PROFILE_PATH.exists():
            return json.loads(CHANNEL_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[ChannelProfile] Lỗi đọc cache: {e}")
    return {}

def _save_profiles(profiles: dict) -> None:
    """Ghi profile cache xuống file JSON."""
    try:
        CHANNEL_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHANNEL_PROFILE_PATH.write_text(
            json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[ChannelProfile] Lỗi ghi cache: {e}")

def get_channel_profile(channel_name: str) -> dict | None:
    """
    Trả về profile đã lưu của kênh (cover_y_percent, cover_percent, voice).
    Trả về None nếu kênh chưa có profile — cần quét OCR.
    """
    profiles = _load_profiles()
    return profiles.get(channel_name)

def save_channel_profile(channel_name: str, cover_y_percent: float, cover_percent: float, voice: str) -> None:
    """
    Lưu profile của kênh vào cache. Chỉ cần gọi 1 lần khi kênh xuất hiện lần đầu.
    Các lần sau sẽ đọc thẳng từ cache mà không cần quét OCR lại.
    """
    profiles = _load_profiles()
    profiles[channel_name] = {
        "cover_y_percent": cover_y_percent,
        "cover_percent": cover_percent,
        "voice": voice,
    }
    _save_profiles(profiles)
    logger.info(f"[ChannelProfile] Đã lưu profile kênh '{channel_name}': y={cover_y_percent}%, h={cover_percent}%, voice={voice}")

def get_default_voice_for_channel(channel_name: str) -> str:
    """Trả về giọng đọc mặc định phù hợp với nhân vật chính của kênh."""
    return CHANNEL_VOICE_MAP.get(channel_name, "vi-VN-NamMinhNeural")

def sanitize_channel_name(author: str, title: str = "") -> str:
    """Chuẩn hóa tên kênh / tác giả thành tên thư mục tiếng Việt dễ nhớ, an toàn trên Windows."""
    clean_author = (author or "").strip()
    clean_title = (title or "").strip()

    # 1. Kiểm tra trong danh bạ kênh đã biết
    for k, vn_name in KNOWN_CHANNELS_VN.items():
        if k.lower() in clean_author.lower() or k.lower() in clean_title.lower():
            return vn_name

    # 2. Nhận diện từ khóa ngữ cảnh
    combined = (clean_author + " " + clean_title).lower()
    if any(w in combined for w in ["二娃", "nhị oa", "nhioa"]):
        return "Kênh Nhị Oa"
    if any(w in combined for w in ["凉皮", "lương bì", "luong bi"]):
        return "Kênh Lương Bì Mẹ Bỉm"
    if any(w in combined for w in ["摆摊", "凉面", "mộng mộng"]):
        return "Kênh Mì Lạnh Xe Đẩy - Mộng Mộng"
    if any(w in combined for w in ["小卖部", "烤肠", "tiệm tạp hóa", "tap hoa"]):
        return "Kênh Tiệm Tạp Hóa - Lưu Băng Băng"
    if any(w in combined for w in ["萌宠", "小主人", "mèo", "thú cưng", "胡德禄"]):
        return "Kênh Mèo Hài Hước - Hồ Đức Lộc"
    if any(w in combined for w in ["摸鱼", "办公室", "关东煮", "văn phòng", "oden"]):
        return "Kênh Ẩm Thực Văn Phòng - Gia Gia"
    if any(w in combined for w in ["桃气", "小竹", "tiểu trúc"]):
        return "Kênh Ăn Vặt Tàu Cao Tốc - Tiểu Trúc"

    if not clean_author or clean_author.lower() in ["unknown", "none", ""]:
        return "Kênh Tổng Hợp"

    # 3. Kênh mới chưa biết: làm sạch ký tự
    safe_name = re.sub(r'[\\/*?:"<>|]', '', clean_author).strip()
    if not safe_name:
        return "Kênh Tổng Hợp"
    if not safe_name.startswith("Kênh"):
        safe_name = f"Kênh {safe_name}"
    return safe_name


def get_channel_output_dir(author: str, title: str = "") -> Path:
    """
    Lấy đường dẫn thư mục xuất video theo từng kênh cụ thể bằng tiếng Việt.
    Tự động tạo thư mục nếu chưa tồn tại.
    """
    folder_name = sanitize_channel_name(author, title)
    channel_dir = OUTPUT_DIR / folder_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir
