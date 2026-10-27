import logging
import math
from pathlib import Path

from config import (
    OUTPUT_WIDTH, OUTPUT_HEIGHT, COVER_POSITION, COVER_PERCENT, COVER_Y_PERCENT,
    COVER_MODE, COVER_COLOR, OUTPUT_DIR, TEMP_DIR, FONT_PATH
)
from utils.ffmpeg import run_ffmpeg, get_video_info

logger = logging.getLogger(__name__)

def resolve_cover_band(height: int, config: dict) -> tuple[int, int]:
    """Tính toán toạ độ y và chiều cao của dải che (Nhận cấu hình đã được xử lý từ main)"""
    
    cover_h_pct = config.get("cover_percent", COVER_PERCENT)
    cover_y_pct = config.get("cover_y_percent", COVER_Y_PERCENT)
    
    cover_h = int(height * cover_h_pct / 100)
    # Tính y sao cho tâm dải che nằm ở khoảng cách cover_y_pct tính từ đáy lên
    top_pct = 100 - cover_y_pct - (cover_h_pct / 2)
    cover_y = int(height * top_pct / 100)
    
    # Đảm bảo không bị tràn ngoài video
    cover_y = max(0, min(height - cover_h, cover_y))
    return cover_y, cover_h

def _build_cover_filter(w: int, h: int, position: str, percent: int, mode: str) -> str:
    """Tạo filter để che phụ đề gốc."""
    cover_h = int(h * percent / 100)
    filters = []
    
    if mode == "drawbox":
        if position in ("top", "both"):
            filters.append(f"drawbox=x=0:y=0:w={w}:h={cover_h}:color=black:t=fill")
        if position in ("bottom", "both"):
            y = h - cover_h
            filters.append(f"drawbox=x=0:y={y}:w={w}:h={cover_h}:color=black:t=fill")
            
    return ",".join(filters) if filters else ""

def _build_crop_filter(w: int, h: int, retention: float = 0.98) -> str:
    """Giữ lại 98% khung hình gốc của video (giữ trọn vẹn toàn bộ khung hình, crop nhẹ 2%)."""
    if retention >= 1.0:
        return ""
    # Cắt nhẹ 2% biên, giữ 98% toàn bộ khung hình (đảm bảo chia hết cho 2)
    crop_w = (int(w * retention) // 2) * 2
    crop_h = (int(h * retention) // 2) * 2
    return f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2"

def _get_crop_strategy(w: int, h: int) -> str:
    """Lấy chiến lược cắt video dựa trên kích thước."""
    ratio = w / h
    if ratio > 1.2:
        return "horizontal_to_vertical"
    if ratio < 0.7:
        return "already_vertical"
    return "square_or_other"

def build_timeline_enable_expression(segments: list, gap_threshold: float = 0.35, pad_start: float = 0.08, pad_end: float = 0.12) -> str:
    """
    Gộp các khoảng thời gian thoại liền kề và tạo biểu thức enable cho FFmpeg:
    Ví dụ: "between(t,0.0,7.85)+between(t,11.5,18.2)"
    """
    if not segments:
        return ""
    
    raw_intervals = []
    for s in segments:
        st = getattr(s, 'start', None) if not isinstance(s, dict) else s.get('start')
        en = getattr(s, 'end', None) if not isinstance(s, dict) else s.get('end')
        if st is not None and en is not None:
            raw_intervals.append([max(0.0, float(st) - pad_start), float(en) + pad_end])
            
    if not raw_intervals:
        return ""
        
    raw_intervals.sort(key=lambda x: x[0])
    
    # Gộp các khoảng cách nhau < gap_threshold để chống nhấp nháy
    merged = []
    cur_st, cur_en = raw_intervals[0]
    for nxt_st, nxt_en in raw_intervals[1:]:
        if nxt_st <= cur_en + gap_threshold:
            cur_en = max(cur_en, nxt_en)
        else:
            merged.append((cur_st, cur_en))
            cur_st, cur_en = nxt_st, nxt_en
    merged.append((cur_st, cur_en))
    
    expr_parts = [f"between(t,{st:.2f},{en:.2f})" for st, en in merged]
    return "+".join(expr_parts)

import subprocess

def get_best_video_encoder() -> tuple[str, list[str]]:
    """Tự động dò tìm bộ mã hóa video bằng phần cứng (GPU) tốt nhất hiện có."""
    for codec, extra_args in [
        ('h264_amf', ['-rc', 'vbr_peak', '-qp_i', '22', '-qp_p', '22', '-quality', 'quality']), # AMD Radeon
        ('h264_nvenc', ['-preset', 'p4', '-cq', '22', '-b:v', '0']),                            # NVIDIA
        ('h264_qsv', ['-preset', 'veryfast', '-global_quality', '22']),                         # Intel QuickSync
        ('libx264', ['-preset', 'fast', '-crf', '20'])                                          # Fallback CPU
    ]:
        if codec == 'libx264':
            logger.info("[GPU Encoder] Không tìm thấy GPU, sử dụng CPU (libx264)")
            return codec, extra_args
        
        # Kiểm tra thử codec có hoạt động trên phần cứng máy này không
        try:
            test_cmd = ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=size=128x128:rate=1:duration=0.1', '-c:v', codec, '-f', 'null', '-']
            proc = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode == 0:
                logger.info(f"[GPU Encoder] Đã kích hoạt Hardware Acceleration thành công: {codec}")
                return codec, extra_args
        except Exception:
            pass
            
    return 'libx264', ['-preset', 'fast', '-crf', '20']

def process_video(
    video_path: Path, 
    audio_path: Path, 
    subtitle_path: Path, 
    config: dict = None, 
    output_path: Path = None, 
    segments: list = None,
    logo_path: Path = None
) -> Path:
    """Xử lý video hoàn chỉnh: làm mờ/che sub gốc theo timeline, cắt, gắn phụ đề, chèn logo và ghép âm thanh."""
    if config is None:
        config = {}
    if output_path is None:
        output_path = OUTPUT_DIR / "output.mp4"
    if logo_path is None:
        logo_path = config.get("logo_path")
        
    cover_position = config.get("cover_position", COVER_POSITION)
    cover_mode = config.get("cover_mode", COVER_MODE)
    cover_percent = config.get("cover_percent", COVER_PERCENT)
    
    info = get_video_info(video_path)
    w = info.width or OUTPUT_WIDTH
    h = info.height or OUTPUT_HEIGHT
    
    # Lấy thông số vùng làm mờ trục Y
    cover_y, cover_h = resolve_cover_band(h, config)
    
    # Xây dựng biểu thức điều kiện hiển thị vùng làm mờ theo dòng thời gian (Smart Blur)
    enable_clause = ""
    if segments:
        enable_expr = build_timeline_enable_expression(segments)
        if enable_expr:
            enable_clause = f":enable='{enable_expr}'"
            logger.info(f"[Video Processor] Kích hoạt Smart Timeline Blur ({len(segments)} segments)")
    
    filter_sections = []
    current_label = "0:v"
    
    # 1. Làm mờ phụ đề tiếng Trung gốc (boxblur) hoặc che thanh đen (drawbox)
    if cover_mode == "boxblur":
        if cover_position in ("bottom", "both"):
            filter_sections.append(
                f"[{current_label}]split[vmain][vsub];"
                f"[vsub]crop=iw:{cover_h}:0:{cover_y},boxblur=luma_radius=18:luma_power=3,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.25:t=fill[vblur];"
                f"[vmain][vblur]overlay=0:{cover_y}{enable_clause}[vcovered]"
            )
            current_label = "vcovered"
        if cover_position in ("top", "both"):
            filter_sections.append(
                f"[{current_label}]split[vmain2][vsub2];"
                f"[vsub2]crop=iw:{cover_h}:0:0,boxblur=luma_radius=18:luma_power=3,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.25:t=fill[vblur2];"
                f"[vmain2][vblur2]overlay=0:0{enable_clause}[vcovered2]"
            )
            current_label = "vcovered2"
    elif cover_mode == "drawbox":
        cover_filter = _build_cover_filter(w, h, cover_position, cover_percent, cover_mode)
        if cover_filter:
            filter_sections.append(f"[{current_label}]{cover_filter}[vcovered]")
            current_label = "vcovered"
            
    # 2. Chuỗi filter tuần tự tiếp theo (Crop 98% -> Scale 1080x1920 -> Pad -> Burn ASS Subtitle)
    linear_filters = []
    
    crop_filter = _build_crop_filter(w, h)
    if crop_filter:
        linear_filters.append(crop_filter)
        
    linear_filters.append(f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease")
    linear_filters.append(f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black")
    
    ass_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
    if FONT_PATH.exists():
        fonts_dir_escaped = str(FONT_PATH.parent).replace('\\', '/').replace(':', '\\:')
        linear_filters.append(f"ass='{ass_path_escaped}':fontsdir='{fonts_dir_escaped}'")
    else:
        linear_filters.append(f"ass='{ass_path_escaped}'")
        
    has_logo = logo_path and Path(logo_path).exists()
    out_video_label = "v_sub" if has_logo else "v"
    
    if filter_sections:
        filter_complex = ";".join(filter_sections) + f";[{current_label}]{','.join(linear_filters)}[{out_video_label}]"
    else:
        filter_complex = f"[{current_label}]{','.join(linear_filters)}[{out_video_label}]"
        
    cmd_inputs = ['ffmpeg', '-i', str(video_path), '-i', str(audio_path)]
    
    # 3. Chèn Logo / Watermark vào góc trái trên cùng
    if has_logo:
        cmd_inputs.extend(['-i', str(logo_path)])
        from config import LOGO_WIDTH, LOGO_HEIGHT, LOGO_MARGIN_X, LOGO_MARGIN_Y
        filter_complex += f";[2:v]scale={LOGO_WIDTH}:{LOGO_HEIGHT}[logo_scaled];[v_sub][logo_scaled]overlay={LOGO_MARGIN_X}:{LOGO_MARGIN_Y}[v]"
        logger.info(f"[Video Processor] Đã kích hoạt chèn Logo góc trái trên ({logo_path})")
        
    # Xác định Codec GPU
    codec, extra_args = get_best_video_encoder()
        
    cmd = cmd_inputs + [
        '-filter_complex', filter_complex,
        '-map', '[v]', '-map', '1:a',
        '-c:v', codec, *extra_args,
        '-threads', '0',
        '-c:a', 'aac', '-b:a', '192k',
        '-r', '30',
        '-movflags', '+faststart',
        '-y', str(output_path)
    ]
    
    run_ffmpeg(cmd)
    
    return output_path


def remux_video_with_audio(video_path: Path, audio_path: Path, output_path: Path = None) -> Path:
    """
    Ghép luồng âm thanh lồng tiếng vào video gốc siêu tốc bằng kỹ thuật Stream Copy (-c:v copy).
    Không nén lại hình ảnh -> Hoàn thành trong 10-20 giây cho video dài 1-2 tiếng!
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "output.mp4"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("[Video Processor] Kích hoạt Stream Copy siêu tốc (-c:v copy), giữ nguyên 100% chất lượng video gốc...")
    
    cmd = [
        'ffmpeg', '-y',
        '-i', str(video_path),
        '-i', str(audio_path),
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest',
        '-movflags', '+faststart',
        str(output_path)
    ]
    run_ffmpeg(cmd, "Fast stream copy remux")
    return output_path

