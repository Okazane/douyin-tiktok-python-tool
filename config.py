from pathlib import Path
from dataclasses import dataclass, field

# Project root
PROJECT_ROOT = Path(__file__).parent

# === Video Output ===
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30

# === Subtitle Cover & Alignment (Trục Y) ===
DEFAULT_COVER_Y_PERCENT = 32.0   # % cách đáy (Tâm dải mờ cách đáy 32%)
DEFAULT_COVER_PERCENT = 12.0     # % chiều cao dải che (12% che trọn vẹn cả phụ đề 1-2 dòng)
TIKTOK_UNSAFE_BOTTOM_PERCENT = 12# Vùng caption+username sát đáy của TikTok (Cảnh báo nếu lấn vào)

COVER_POSITION = "bottom"        # bottom | top | both
COVER_PERCENT = DEFAULT_COVER_PERCENT
COVER_Y_PERCENT = DEFAULT_COVER_Y_PERCENT
COVER_MODE = "boxblur"           # boxblur (làm mờ mịn màng) | drawbox (thanh đen)
COVER_COLOR = "black"

# === Channel Presets (Khóa cứng cấu hình chuẩn theo từng Kênh) ===
CHANNEL_PRESETS = {
    "erwa": {
        "name": "Kênh Nhị Oa (二娃)",
        "cover_y_percent": 32.0,
        "cover_percent": 12.0,
        "cover_mode": "boxblur",
        "voice": "vi-VN-NamMinhNeural",
    },
    "nhioa": {
        "name": "Kênh Nhị Oa (二娃)",
        "cover_y_percent": 32.0,
        "cover_percent": 12.0,
        "cover_mode": "boxblur",
        "voice": "vi-VN-NamMinhNeural",
    },
    "二娃": {
        "name": "Kênh Nhị Oa (二娃)",
        "cover_y_percent": 32.0,
        "cover_percent": 12.0,
        "cover_mode": "boxblur",
        "voice": "vi-VN-NamMinhNeural",
    }
}

# === Audio & Mixing (3-Track Studio Mix) ===
AUDIO_MODE = "tts_with_bgm"     # tts_with_bgm | subtitle_only
BGM_VOLUME = 0.22               # 22% volume cho nhạc nền YouTube chill
ORIGINAL_AUDIO_VOLUME = 0.18    # 18% volume giữ tiếng môi trường / nấu ăn gốc Douyin
TTS_VOLUME = 1.6                # 160% volume TTS (giọng đọc to, rõ, nổi bật nhất)

# === Custom BGM (Nhạc nền YouTube mặc định cho mọi video) ===
BGM_DIR = PROJECT_ROOT / "assets" / "bgm"
BGM_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_BGM_PATH = BGM_DIR / "default_bgm.mp3"
DEFAULT_BGM_URL = "https://www.youtube.com/watch?v=yk919HORd5Y"

# === TTS (Giọng đọc chuẩn TikTok) ===
TTS_ENGINE = "edge"                    # edge (Edge-TTS Neural) | melo (MeloTTS)
TTS_VOICE_FEMALE = "vi-VN-HoaiMyNeural"  # Giọng Nữ TikTok quốc dân (Hoài My)
TTS_VOICE_MALE = "vi-VN-NamMinhNeural"   # Giọng Nam truyền cảm (Nam Minh)
TTS_VOICE = TTS_VOICE_MALE             # Mặc định: Nam Minh
TTS_RATE = "+15%"                      # Default speed (~1.15x chuẩn vlog ẩm thực)
TTS_MAX_RATE = "+80%"                  # Max speed when compressing
MELO_SPEAKER = "VI-default"            # MeloTTS speaker (dự phòng)


# === Whisper ===
WHISPER_MODEL = "medium"         # tiny | base | small | medium | large-v2 | large-v3
WHISPER_LANGUAGE = "zh"
MIN_WORDS_THRESHOLD = 5          # Below this = no speech detected

# === Subtitle Style (ASS) ===
FONT_NAME = "Be Vietnam Pro"
FONT_SIZE = 70
FONT_COLOR = "&H0000FFFF"       # Yellow
HIGHLIGHT_COLOR = "&H0000FFFF"  # Yellow (karaoke highlight)
OUTLINE_COLOR = "&H00000000"    # Black outline
OUTLINE_WIDTH = 4
SUB_MARGIN_BOTTOM = 480         # px from bottom (nằm ngay dưới video, tránh bị che bởi thanh nút TikTok)

# === AI Translation (Gemini / LLM) ===
AI_KEY_FILE = PROJECT_ROOT / "gemini_key.txt"
GEMINI_API_KEY = ""  # Lấy miễn phí tại https://aistudio.google.com/
AI_TRANSLATOR_MODEL = "gemini-flash-lite-latest"  # gemini-flash-lite-latest / gemini-2.5-flash-lite

# === Douyin Account / Cookies ===
COOKIE_FILE = PROJECT_ROOT / "cookies.txt"
DOUYIN_COOKIE = ""  # Có thể dán chuỗi cookie trực tiếp vào đây hoặc lưu trong cookies.txt

# === Logo / Watermark ===
DEFAULT_LOGO_PATH = Path(r"D:\watermarked_img_17556575374072665996.jpg")
LOGO_WIDTH = 140
LOGO_HEIGHT = 140
LOGO_MARGIN_X = 45
LOGO_MARGIN_Y = 65

# === Cache ===
CACHE_ENABLED = True
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp"
ASSETS_DIR = PROJECT_ROOT / "assets"
FONT_PATH = ASSETS_DIR / "fonts" / "BeVietnamPro-Bold.ttf"

# Tạo directories nếu chưa có
for d in [CACHE_DIR, OUTPUT_DIR, TEMP_DIR, ASSETS_DIR / "fonts"]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class PipelineConfig:
    """Cấu hình cho 1 lần chạy pipeline."""
    input_source: str
    mode: str = AUDIO_MODE
    tts_engine: str = TTS_ENGINE
    cover_position: str = COVER_POSITION
    cover_percent: int = COVER_PERCENT
    cover_y_percent: int = COVER_Y_PERCENT
    cover_mode: str = COVER_MODE
    voice: str = TTS_VOICE
    whisper_model: str = WHISPER_MODEL
    output_path: str | None = None
    logo_path: Path | None = DEFAULT_LOGO_PATH
    bgm_path: Path | str | None = DEFAULT_BGM_PATH
    no_sub: bool = False

    def __post_init__(self):
        if self.output_path is None:
            self.output_path = str(OUTPUT_DIR / "output.mp4")
