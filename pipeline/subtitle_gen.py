import logging
from pathlib import Path
import pysubs2

from config import (
    FONT_NAME, FONT_SIZE, FONT_COLOR, HIGHLIGHT_COLOR, 
    OUTLINE_COLOR, OUTLINE_WIDTH, SUB_MARGIN_BOTTOM, 
    OUTPUT_WIDTH, OUTPUT_HEIGHT, FONT_PATH, TEMP_DIR, 
    COVER_PERCENT, COVER_Y_PERCENT
)

logger = logging.getLogger(__name__)

def calculate_sub_margin(w: int, h: int, target_w: int = OUTPUT_WIDTH, target_h: int = OUTPUT_HEIGHT, cover_percent: int = COVER_PERCENT, cover_y_percent: int = COVER_Y_PERCENT) -> int:
    """
    Tính toán MarginV (tính từ đáy màn hình target_h lên) để chữ nằm đè khớp lên vùng che.
    Giai đoạn 2: Dựa trên cover_y_percent (cách đáy) và cover_percent (chiều cao dải che)
    """
    scale = min(target_w / w, target_h / h)
    scaled_h = int(h * scale)
    pad_y = (target_h - scaled_h) // 2
    
    # 1. Tính toán vùng che trên video gốc đã scale (scaled_h)
    cover_h = int(scaled_h * cover_percent / 100)
    top_pct = 100 - cover_y_percent - (cover_percent / 2)
    cover_y = int(scaled_h * top_pct / 100)
    
    # 2. Tâm của dải che (tính từ đỉnh của scaled_h)
    band_center_y = cover_y + cover_h / 2
    
    # 3. Ước lượng chiều cao 1 dòng text và tính toạ độ đáy chữ
    text_height = FONT_SIZE * 1.2
    text_bottom_y = band_center_y + text_height / 2
    
    # 4. Tính khoảng cách từ mép dưới của video (scaled_h) đến đáy chữ
    margin_v_video = scaled_h - text_bottom_y
    
    # 5. MarginV thực tế (tính từ đáy target_h) = margin trong video + khoảng pad đen
    margin_v = margin_v_video + pad_y
    
    return max(0, int(margin_v))

def generate_ass(segments: list, output_path: Path = None, video_size: tuple[int, int] | None = None, margin_v: int | None = None) -> Path:
    """Tạo phụ đề định dạng ASS đặt thẳng bên trong khung hình video."""
    if output_path is None:
        output_path = TEMP_DIR / "subtitles.ass"
        
    if margin_v is None:
        if video_size:
            margin_v = calculate_sub_margin(video_size[0], video_size[1])
        else:
            margin_v = SUB_MARGIN_BOTTOM
        
    subs = pysubs2.SSAFile()
    subs.info['PlayResX'] = OUTPUT_WIDTH
    subs.info['PlayResY'] = OUTPUT_HEIGHT
    
    style = pysubs2.SSAStyle(
        fontname=FONT_NAME,
        fontsize=FONT_SIZE,
        primarycolor=pysubs2.Color(255, 255, 255, 0),  # White
        outlinecolor=pysubs2.Color(0, 0, 0, 0),  # Black
        backcolor=pysubs2.Color(0, 0, 0, 128),  # Semi-transparent black background
        outline=OUTLINE_WIDTH,
        shadow=1,
        alignment=2,  # Bottom center
        marginv=margin_v,
        bold=True,
    )
    
    subs.styles["Default"] = style
    
    for segment in segments:
        start_ms = int(segment.start * 1000)
        end_ms = int(segment.end * 1000)
        
        text = f"{{\\fad(200,200)}}{segment.translated_text}"
        
        event = pysubs2.SSAEvent(
            start=start_ms,
            end=end_ms,
            text=text
        )
        subs.events.append(event)
        
    subs.save(str(output_path))
    return output_path

def generate_srt(segments: list, output_path: Path = None) -> Path:
    """Tạo phụ đề định dạng SRT."""
    if output_path is None:
        output_path = TEMP_DIR / "subtitles.srt"
        
    subs = pysubs2.SSAFile()
    
    for segment in segments:
        start_ms = int(segment.start * 1000)
        end_ms = int(segment.end * 1000)
        
        event = pysubs2.SSAEvent(
            start=start_ms,
            end=end_ms,
            text=segment.translated_text
        )
        subs.events.append(event)
        
    subs.save(str(output_path))
    return output_path
