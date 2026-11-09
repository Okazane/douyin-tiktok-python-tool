"""
Vocal Separator module using audio-separator (ONNX CPU Mode).
Tách riêng Vocal tiếng Trung và Background BGM từ âm thanh video gốc.
"""
import logging
from pathlib import Path
from config import TEMP_DIR

logger = logging.getLogger(__name__)

_separator_instance = None

def get_vocal_separator(output_dir: Path = None):
    """Khởi tạo singleton Audio Separator (ONNX CPU)."""
    global _separator_instance
    if _separator_instance is None:
        from audio_separator.separator import Separator
        out_path = str(output_dir or TEMP_DIR / "separated")
        Path(out_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"[AudioSeparator] Khởi động AI tách vocal (CPU ONNX mode) tại {out_path}...")
        _separator_instance = Separator(output_dir=out_path, output_format="WAV")
        _separator_instance.load_model(model_filename="MDX23C-8KFFT-InstVoc_HQ.ckpt")
    return _separator_instance

def separate_vocals(audio_path: Path, output_dir: Path = None) -> tuple[Path, Path]:
    """
    Tách âm thanh thành 2 file: (Instrumental / BGM, Vocal).
    Trả về: (bgm_path, vocal_path)
    """
    try:
        sep = get_vocal_separator(output_dir)
        output_files = sep.separate(str(audio_path))
        out_dir = Path(output_dir or TEMP_DIR / "separated")
        
        # Thường audio-separator trả về [Instrumental, Vocals]
        inst_path = out_dir / output_files[0] if len(output_files) > 0 else audio_path
        vocal_path = out_dir / output_files[1] if len(output_files) > 1 else audio_path
        
        logger.info(f"[AudioSeparator] ✅ Đã tách thành công: BGM={inst_path.name}, Vocal={vocal_path.name}")
        return inst_path, vocal_path
    except Exception as e:
        logger.warning(f"[AudioSeparator] Không thể tách vocal (dùng audio gốc): {e}")
        return audio_path, audio_path
