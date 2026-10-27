"""FFmpeg wrapper utilities."""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    codec: str

def check_ffmpeg() -> bool:
    """Kiểm tra ffmpeg có trong PATH không."""
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def run_ffmpeg(args: list[str], desc: str = "") -> subprocess.CompletedProcess:
    """Run ffmpeg command with error handling."""
    if desc:
        logger.debug(f"Running ffmpeg cho (for) {desc}: {' '.join(args)}")
    else:
        logger.debug(f"Running ffmpeg: {' '.join(args)}")
    
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg lỗi (error): {result.stderr}")
    return result

def get_video_info(path: Path) -> VideoInfo:
    """Sử dụng ffprobe để lấy thông tin video."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    
    video_stream = None
    audio_stream = None
    
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not video_stream:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and not audio_stream:
            audio_stream = stream
            
    if not video_stream:
        raise ValueError("Không tìm thấy luồng video (no video stream found)")
        
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    
    # Tính FPS
    fps = 0.0
    r_frame_rate = video_stream.get("r_frame_rate", "0/1")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/")
        if float(den) != 0:
            fps = float(num) / float(den)
            
    # Lấy duration
    duration = float(data.get("format", {}).get("duration", 0.0))
    
    codec = video_stream.get("codec_name", "")
    has_audio = audio_stream is not None
    
    return VideoInfo(
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        has_audio=has_audio,
        codec=codec
    )

def extract_audio(video_path: Path, output_path: Path) -> Path:
    """Trích xuất audio (WAV 44100Hz mono) từ video."""
    cmd = [
        "ffmpeg", "-i", str(video_path), "-vn",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
        str(output_path), "-y"
    ]
    run_ffmpeg(cmd, "extract audio")
    return output_path

def get_audio_duration(path: Path) -> float:
    """Sử dụng ffprobe để lấy thời lượng audio."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0.0))
