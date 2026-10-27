"""
OCR-Whisper Phonetic Fusion Aligner (Pillar 2).
Uses PaddleOCR multi-frame sampling, image preprocessing, and semantic fusion with number preservation.
"""
import logging
from pathlib import Path
from pipeline.transcriber import Segment
from pipeline.vision_ocr import ocr_all_segments, ocr_frame
from pipeline.fusion import fuse_segments
from pipeline.model_cache import MODEL_CACHE
import cv2

logger = logging.getLogger(__name__)

def verify_subtitle_band(video_path: Path, cover_y_percent: float, cover_percent: float, sample_timestamps: list[float]) -> bool:
    """
    Kiểm chứng xem toạ độ dải phụ đề có thực sự chứa văn bản không bằng PaddleOCR.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False
        
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    
    top_pct = 100 - cover_y_percent - (cover_percent / 2)
    y1 = max(0, int(height * top_pct / 100))
    y2 = min(height, y1 + int(height * cover_percent / 100))
    
    ocr = MODEL_CACHE.ocr
    valid_count = 0
    
    for t in sample_timestamps[:4]:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
            
        crop_img = frame[y1:y2, 0:width]
        items = ocr_frame(ocr, crop_img)
        if items:
            valid_count += 1
            
    cap.release()
    return valid_count >= 1

def extract_and_fuse_segments(
    video_path: Path,
    segments: list[Segment],
    cover_y_percent: float = 0.0,
    cover_percent: float = 0.0,
    context: str = "",
    glossary: dict = None
) -> list[Segment]:
    """
    Trích xuất chữ từ video bằng PaddleOCR và dung hợp thông minh với Whisper.
    """
    if not segments:
        return segments
        
    logger.info(f"[OCR Aligner] Bắt đầu quét PaddleOCR cho {len(segments)} đoạn thoại (Preprocess + Confidence Filter)...")
    
    # Chuẩn bị segments theo định dạng dict
    whisper_data = [
        {
            "id": s.id,
            "start": s.start,
            "end": s.end,
            "zh_text": s.text,
            "confidence": s.confidence
        }
        for s in segments
    ]
    
    # 1. OCR toàn bộ segments
    ocr_results = ocr_all_segments(
        video_path=video_path,
        segments=whisper_data,
        min_conf=0.80,
        bottom_start=0.55,
        min_seen=1
    )
    
    # 2. Dung hợp (Semantic Fusion) bảo tồn số và đơn vị
    fused_data = fuse_segments(
        whisper_segments=whisper_data,
        ocr_results=ocr_results,
        context=context,
        glossary=glossary
    )
    
    # 3. Gán lại kết quả vào Segment objects
    fused_segments = []
    for d in fused_data:
        fused_segments.append(Segment(
            id=d["id"],
            start=d["start"],
            end=d["end"],
            text=d["zh_text"],
            confidence=d["confidence"]
        ))
        
    return fused_segments
