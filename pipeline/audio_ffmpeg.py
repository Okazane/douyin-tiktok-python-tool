"""
FFmpeg Audio Processing with Sidechain Ducking, Fade-in/out, and 2-Pass Loudnorm.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


logger = logging.getLogger(__name__)

def _run_cmd(cmd: List[str]) -> str:
    """Chạy FFmpeg command, raise RuntimeError nếu lỗi."""
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(map(str, cmd))}\n"
            f"STDERR:\n{proc.stderr[-3000:]}"
        )
    return proc.stdout

def extract_audio(
    video_path: Union[str, Path],
    out_wav: Union[str, Path],
    sample_rate: int = 48000,
    channels: int = 2,
) -> Path:
    """Tách audio từ video với format chuẩn."""
    _run_cmd(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            str(out_wav),
        ]
    )
    return Path(out_wav)


def _build_single_voice_chunk(
    segments: List[Dict[str, Any]],
    output_wav: Path,
    fade_duration: float,
    total_duration: Optional[float] = None
) -> Path:

    inputs: List[str] = []
    filters: List[str] = []
    labels: List[str] = []

    for i, seg in enumerate(segments):
        f = Path(seg["file"])
        if not f.exists():
            raise FileNotFoundError(f"TTS file not found: {f}")

        ms = int(float(seg["start"]) * 1000)
        inputs.extend(["-i", str(f)])

        seg_dur = float(seg.get("duration", 2.0))
        slot_dur = float(seg.get("slot_duration", seg_dur))
        allowed_dur = float(seg.get("allowed_duration", slot_dur))
        atempo = float(seg.get("atempo", 1.0))

        # Nếu có atempo > 1.0, tính effective_duration sau khi tăng tốc
        if atempo > 1.0:
            effective_dur = seg_dur / atempo
        else:
            effective_dur = min(seg_dur, allowed_dur)
        out_fade_start = max(0.01, effective_dur - fade_duration)

        # Xây dựng chuỗi filter — chèn atempo nếu cần
        atempo_filter = ""
        if atempo > 1.0:
            # FFmpeg atempo chỉ hỗ trợ 0.5 - 100.0, nhưng > 2.0 cần chain
            if atempo <= 2.0:
                atempo_filter = f"atempo={atempo:.3f},"
            else:
                # Chain nhiều atempo filters (mỗi cái tối đa 2.0)
                parts = []
                remaining = atempo
                while remaining > 1.0:
                    factor = min(2.0, remaining)
                    parts.append(f"atempo={factor:.3f}")
                    remaining /= factor
                atempo_filter = ",".join(parts) + ","

        filters.append(
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"{atempo_filter}"
            f"afade=t=in:st=0:d={fade_duration},"
            f"afade=t=out:st={out_fade_start:.3f}:d={fade_duration},"
            f"atrim=end={effective_dur:.3f},"
            f"adelay={ms}|{ms}[a{i}]"
        )
        labels.append(f"[a{i}]")

    mix_inputs = "".join(labels)
    duration_filter = ""
    if total_duration:
        duration_filter = f",apad=whole_dur={float(total_duration):.3f},atrim=end={float(total_duration):.3f}"

    filter_complex = (
        ";".join(filters) + ";" +
        f"{mix_inputs}amix=inputs={len(segments)}:duration=longest:normalize=0,"
        f"aresample=48000{duration_filter}[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(output_wav),
    ]

    _run_cmd(cmd)
    return output_wav



def _mix_wav_chunks(chunk_files: List[Path], output_wav: Path, total_duration: Optional[float] = None) -> Path:
    inputs = []
    labels = []
    for i, cf in enumerate(chunk_files):
        inputs.extend(["-i", str(cf)])
        labels.append(f"[{i}:a]")

    mix_inputs = "".join(labels)
    duration_filter = ""
    if total_duration:
        duration_filter = f",apad=whole_dur={float(total_duration):.3f},atrim=end={float(total_duration):.3f}"

    filter_complex = f"{mix_inputs}amix=inputs={len(chunk_files)}:duration=longest:normalize=0,aresample=48000{duration_filter}[out]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(output_wav),
    ]
    _run_cmd(cmd)
    return output_wav


def build_voice_track_with_fades(
    segments: List[Dict[str, Any]],
    output_wav: Union[str, Path],
    fade_duration: float = 0.05,
    fade_ms: Optional[int] = None,
    total_duration: Optional[float] = None
) -> Path:
    """
    Tạo Voice Track hoàn chỉnh với 50ms fade in/out cho từng segment.
    Tự động chia chunk 40 segments và dùng -filter_complex_script để không bao giờ bị tràn giới hạn dòng lệnh Windows.
    """
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    if fade_ms is not None:
        fade_duration = max(0.001, fade_ms / 1000.0)
    else:
        fade_duration = max(0.001, float(fade_duration))


    if not segments:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:a", "pcm_s16le"
        ]
        if total_duration:
            cmd.extend(["-t", str(total_duration)])
        else:
            cmd.extend(["-t", "1"])
        cmd.append(str(output_wav))
        _run_cmd(cmd)
        return output_wav

    CHUNK_SIZE = 40


    if len(segments) > CHUNK_SIZE:
        chunk_files = []
        for c_idx, start_idx in enumerate(range(0, len(segments), CHUNK_SIZE)):
            chunk_segs = segments[start_idx:start_idx + CHUNK_SIZE]
            chunk_wav = output_wav.parent / f"voice_chunk_{c_idx:03d}.wav"
            _build_single_voice_chunk(chunk_segs, chunk_wav, fade_duration, total_duration)
            chunk_files.append(chunk_wav)

        _mix_wav_chunks(chunk_files, output_wav, total_duration)

        for cw in chunk_files:
            try:
                cw.unlink(missing_ok=True)
            except Exception:
                pass
        return output_wav
    else:
        return _build_single_voice_chunk(segments, output_wav, fade_duration, total_duration)


def mix_audio_ducking_two_pass(
    original_audio: Union[str, Path],
    voice_track: Union[str, Path],
    output_audio: Union[str, Path],
    bgm_audio: Optional[Union[str, Path]] = None,
    bg_volume: float = 0.18,      # Âm lượng môi trường gốc Douyin
    bgm_volume: float = 0.22,     # Âm lượng nhạc nền YouTube
    voice_volume: float = 1.6,    # Âm lượng giọng TTS Nam Minh
    total_duration: Optional[float] = None,
    target_lufs: float = -16.0,
    threshold: float = 0.03,
    ratio: float = 8.0,
    attack: float = 30.0,
    release: float = 700.0,
) -> Path:
    """
    Hòa âm 3 luồng chuyên nghiệp: Âm thanh môi trường gốc + Nhạc nền YouTube + Giọng đọc TTS
    kèm Sidechain Ducking và chuẩn hóa 2-Pass EBU R128 (-16 LUFS).
    """
    original_audio = Path(original_audio)
    voice_track = Path(voice_track)
    output_audio = Path(output_audio)
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    
    inputs = ["-i", str(original_audio)]
    
    if bgm_audio and Path(bgm_audio).exists():
        inputs.extend(["-i", str(bgm_audio)])
        has_bgm = True
        voice_idx = 2  # orig=0, bgm=1, voice=2
    else:
        has_bgm = False
        voice_idx = 1  # orig=0, voice=1
        
    inputs.extend(["-i", str(voice_track)])
    
    fade_filter = ""
    if total_duration and total_duration > 5.0:
        fade_start = max(0.1, total_duration - 3.0)
        fade_filter = f",afade=t=out:st={fade_start:.2f}:d=3.0"
        
    if has_bgm:
        bg_build = (
            f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={bg_volume}[orig];"
            f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={bgm_volume}{fade_filter}[bgm_chill];"
            f"[orig][bgm_chill]amix=inputs=2:duration=first:normalize=0[bg_combined];"
        )
        bg_label = "[bg_combined]"
    else:
        bg_build = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={bg_volume}[bg];"
        bg_label = "[bg]"
        
    # FIX: asplit voice stream into 2 copies — [voice_sc] for sidechain detection,
    # [voice_mix] for final mix. Without this, [voice] is consumed by sidechaincompress
    # and becomes an empty stream in amix, causing ALL TTS audio to be silent (-91 dB).
    measure_complex = (
        bg_build +
        f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={voice_volume}[voice];"
        f"[voice]asplit=2[voice_sc][voice_mix];"
        f"{bg_label}[voice_sc]sidechaincompress=threshold={threshold}:ratio={ratio}:attack={attack}:release={release}:level_sc=1[bgduck];"
        f"[bgduck][voice_mix]amix=inputs=2:duration=longest:normalize=0,"
        f"loudnorm=print_format=json[aout]"
    )
    
    measure_cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", measure_complex,
        "-map", "[aout]",
        "-f", "null", "-"
    ]
    
    proc = subprocess.run(measure_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    stats = {}
    if proc.stderr:
        lines = proc.stderr.strip().split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            if "{" in line:
                in_json = True
            if in_json:
                json_lines.append(line)
            if "}" in line and in_json:
                try:
                    stats = json.loads("\n".join(json_lines))
                    break
                except Exception:
                    json_lines = []
                    in_json = False
                    
    if stats and "input_i" in stats:
        logger.info(f"[Audio Ducking] 2-Pass Stats: Input I={stats.get('input_i')}, TP={stats.get('input_tp')}, LRA={stats.get('input_lra')}")
        loudnorm_filter = (
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
            f"measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats.get('input_thresh', -34)}:"
            f"linear=true,aresample=48000[aout]"
        )
    else:
        logger.warning("[Audio Ducking] Không lấy được stats từ Pass 1, fallback về 1-Pass loudnorm.")
        loudnorm_filter = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11,aresample=48000[aout]"
        
    final_complex = (
        bg_build +
        f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={voice_volume}[voice];"
        f"[voice]asplit=2[voice_sc][voice_mix];"
        f"{bg_label}[voice_sc]sidechaincompress=threshold={threshold}:ratio={ratio}:attack={attack}:release={release}:level_sc=1[bgduck];"
        f"[bgduck][voice_mix]amix=inputs=2:duration=longest:normalize=0,"
        + loudnorm_filter
    )
    
    if output_audio.suffix.lower() == ".wav":
        codec_args = ["-c:a", "pcm_s16le"]
    else:
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
        
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", final_complex,
        "-map", "[aout]",
        *codec_args,
        "-ar", "48000",
        str(output_audio),
    ]
    _run_cmd(cmd)
    return output_audio
