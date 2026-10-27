import logging
from pathlib import Path
from config import BGM_VOLUME, ORIGINAL_AUDIO_VOLUME, TTS_VOLUME, DEFAULT_BGM_PATH, TEMP_DIR
from utils.ffmpeg import extract_audio, get_audio_duration as ffmpeg_get_audio_duration
from pipeline.audio_ffmpeg import build_voice_track_with_fades, mix_audio_ducking_two_pass

logger = logging.getLogger(__name__)

def mix_audio(video_path: Path, tts_results: list | None, mode: str, total_duration: float = None, bgm_path: Path | str | None = DEFAULT_BGM_PATH) -> Path:
    """
    Hòa âm 3 luồng Studio: Âm thanh môi trường gốc + Nhạc nền YouTube + Giọng đọc TTS
    kèm Sidechain Ducking + Chuẩn hóa 2-Pass Loudnorm EBU R128 (-16 LUFS).
    """
    original_audio = TEMP_DIR / "original_audio.wav"
    extract_audio(video_path, original_audio)
    
    if mode == "subtitle_only" or not tts_results:
        return original_audio, []
        
    if mode == "tts_with_bgm":
        if total_duration is None:
            total_duration = ffmpeg_get_audio_duration(original_audio)
            
        # Dùng Global Scheduler để tính toán start và allowed_duration cho toàn bộ
        from pipeline.voice_scheduler import schedule_voice_timeline
        segments_data = schedule_voice_timeline(tts_results)
            
        voice_track = TEMP_DIR / "voice_track.wav"
        logger.info(f"[Audio Mixer] Đang dựng Voice Track hoàn chỉnh với 50ms Fade-in/out ({len(segments_data)} đoạn)...")
        build_voice_track_with_fades(
            segments=segments_data,
            output_wav=voice_track,
            total_duration=total_duration,
            fade_duration=0.05
        )
        
        mixed_audio = TEMP_DIR / "mixed_audio.wav"
        
        if bgm_path and str(bgm_path).strip().lower() in ["none", "no", "false", "off", "0", ""]:
            bgm_file = None
        else:
            bgm_file = Path(bgm_path) if bgm_path else DEFAULT_BGM_PATH

        if bgm_file and bgm_file.exists():
            logger.info(f"[Audio Mixer] Hòa âm 3-Track: Tiếng gốc ({ORIGINAL_AUDIO_VOLUME*100:.0f}%) + Nhạc YouTube ({BGM_VOLUME*100:.0f}%) + Voice ({TTS_VOLUME*100:.0f}%)...")
        else:
            logger.info(f"[Audio Mixer] Hòa âm 2-Track: Tiếng gốc + Voice ({TTS_VOLUME*100:.0f}%) (Không dùng nhạc nền BGM)...")
            bgm_file = None

            
        mix_audio_ducking_two_pass(
            original_audio=original_audio,
            voice_track=voice_track,
            output_audio=mixed_audio,
            bgm_audio=bgm_file,
            bg_volume=ORIGINAL_AUDIO_VOLUME,
            bgm_volume=BGM_VOLUME,
            voice_volume=TTS_VOLUME,
            total_duration=total_duration,
            target_lufs=-16.0,
            threshold=0.03,
            ratio=8.0,
            attack=30.0,
            release=700.0
        )
        
        return mixed_audio, segments_data
