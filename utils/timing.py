"""Timing utilities for TTS synchronization."""

import json
import subprocess
import wave
from pathlib import Path
from .ffmpeg import run_ffmpeg

# Tốc độ đọc thực đo của Edge-TTS giọng Việt (âm tiết/giây) ở rate=+0%
# Đo thực tế: Hoài My ~13.2, Nam Minh ~13.5 → dùng 13.0 để có margin an toàn
_EDGE_TTS_SYLLABLES_PER_SEC = 13.0

def estimate_tts_duration(text: str, rate_percent: int = 15) -> float:
    """
    Ước lượng thời lượng TTS Edge-TTS tiếng Việt mà KHÔNG cần gọi API.
    Dựa trên: tiếng Việt mỗi từ ≈ 1 âm tiết, Edge-TTS đọc ~13 âm tiết/giây ở tốc độ gốc.
    Mặc định rate_percent=15 (+15% chuẩn vlog).

    Args:
        text: Câu tiếng Việt cần ước lượng.
        rate_percent: Tốc độ tăng (15 = +15%, 40 = +40%). Dương = nhanh hơn.

    Returns:
        Ước lượng thời lượng tính bằng giây.
    """
    syllables = len(text.split())
    speed = _EDGE_TTS_SYLLABLES_PER_SEC * (1 + rate_percent / 100)
    return max(0.1, syllables / speed)


def calculate_tts_rate(target_duration: float, actual_duration: float, base_rate: int = 15, max_rate: int = 80) -> str:
    """
    Tính toán tốc độ Edge TTS dựa trên mốc tốc độ cơ sở base_rate (+15%).
    Nếu actual <= target * 1.05, giữ nguyên base_rate (ví dụ '+15%').
    Nếu actual > target * 1.05, tính % cần tăng thêm tốc độ để khớp thời lượng.
    Tối đa bằng max_rate (+80%).
    """
    if actual_duration <= target_duration * 1.05:
        if actual_duration < target_duration * 0.6:
            return "+0%"
        return f"+{base_rate}%"
    
    current_speed = 1.0 + (base_rate / 100.0)
    needed_speed = (actual_duration / target_duration) * current_speed
    rate = int((needed_speed - 1.0) * 100)
    rate = min(max(base_rate, rate), max_rate)
    return f"+{rate}%"


def generate_silence(duration: float, output_path: Path, sample_rate: int = 44100) -> Path:
    """Tạo một file WAV không có âm thanh với thời lượng chỉ định bằng ffmpeg."""
    cmd = [
        "ffmpeg", "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", str(duration),
        str(output_path), "-y"
    ]
    run_ffmpeg(cmd, "generate silence")
    return output_path

def _get_wav_duration_fast(path: Path) -> float:
    """Đọc duration WAV cực nhanh bằng Python wave module (không cần spawn ffprobe subprocess)."""
    try:
        with wave.open(str(path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        pass
    return 0.0

def get_media_duration(path: Path) -> float:
    """Lấy thời lượng (duration) của file media. WAV dùng Python wave (nhanh), file khác dùng ffprobe."""
    if path.suffix.lower() == '.wav' and path.exists():
        dur = _get_wav_duration_fast(path)
        if dur > 0:
            return dur
    # Fallback ffprobe cho MP3, MP4, và các định dạng khác
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0.0))
