"""
Vision OCR module using Multi-threading Preprocessing and Subtitle Area Filtering.
"""
import cv2
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pipeline.model_cache import MODEL_CACHE

logger = logging.getLogger(__name__)

def preprocess_frame_for_ocr(frame: np.ndarray) -> np.ndarray:
    """
    Tiền xử lý frame để tăng độ tương phản và nét chữ cho OCR.
    Tối ưu cho RAM 24GB & chip 8745H.
    """
    h, w = frame.shape[:2]
    # Giới hạn kích thước tối đa 1600px để giữ nguyên độ phân giải HD
    if max(h, w) > 1600:
        scale = 1600.0 / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        
    # Tăng độ nét nhẹ (Unsharp Mask Kernel)
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharpened = cv2.filter2D(frame, -1, kernel)
    return sharpened

def _normalize_ocr_text(text: str) -> str:
    """Chuẩn hóa text OCR để gom cụm (group) các kết quả trùng nhau."""
    return "".join(text.split()).lower()

def ocr_frame(ocr, frame: np.ndarray) -> List[Dict[str, Any]]:
    """
    OCR 1 frame hình ảnh BGR.
    Tối ưu: Chỉ quét 45% phần dưới video (nơi chứa phụ đề) -> Tốc độ nhanh gấp 8 lần.
    """
    h, w = frame.shape[:2]
    y_offset = int(h * 0.52)
    crop_frame = frame[y_offset:, :]
    
    try:
        results = ocr.readtext(crop_frame, detail=1, paragraph=False)
    except Exception as e:
        logger.warning(f"Lỗi OCR frame: {e}")
        return []
        
    items = []
    if not results:
        return items
        
    for bbox, text, conf in results:
        text = (text or "").strip()
        if len(text) < 1:
            continue
            
        xs = [p[0] for p in bbox]
        ys = [p[1] + y_offset for p in bbox]
        
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        bh = max(0.0, float(y_max - y_min))
        
        items.append({
            "text": text,
            "confidence": float(conf),
            "box": [float(x_min), float(y_min), float(x_max), float(y_max)],
            "y_max": float(y_max),
            "height": bh,
        })
        
    return items

def filter_subtitle_items(
    items: List[Dict[str, Any]],
    frame_h: int,
    frame_w: int,
    min_conf: float = 0.50,
    bottom_start: float = 0.55,
    min_text_height: float = 0.015,
    max_text_height: float = 0.25,
) -> List[Dict[str, Any]]:
    """Lọc bỏ các text rác, chỉ giữ lại phụ đề ở phần dưới màn hình."""
    out = []
    for it in items:
        if it["confidence"] < min_conf:
            continue
        if it["y_max"] < frame_h * bottom_start:
            continue
            
        rel_h = it["height"] / max(1, frame_h)
        if rel_h < min_text_height or rel_h > max_text_height:
            continue
            
        out.append(it)
    return out

def sample_frames_at_times(video_path: Union[str, Path], times: List[float]) -> List[Tuple[float, np.ndarray]]:
    """Trích xuất khung hình tại các mốc giây chỉ định."""
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    try:
        for t in sorted(set(times)):
            ms = max(0, float(t) * 1000.0)
            cap.set(cv2.CAP_PROP_POS_MSEC, ms)
            ret, frame = cap.read()
            if ret:
                frames.append((float(t), frame))
    finally:
        cap.release()
    return frames

def ocr_segment(
    video_path: Union[str, Path],
    start: float,
    end: float,
    ocr=None,
    min_conf: float = 0.50,
    bottom_start: float = 0.55,
    min_seen: int = 1,
) -> Optional[Dict[str, Any]]:
    """Quét OCR tại các mốc của 1 câu thoại."""
    if ocr is None:
        ocr = MODEL_CACHE.ocr
        
    start, end = float(start), float(end)
    if end <= start:
        return None
        
    mid = (start + end) / 2.0
    times = sorted({
        max(start, mid - 0.18),
        mid,
        min(end, mid + 0.18),
    })
    
    raw_frames = sample_frames_at_times(video_path, times)
    if not raw_frames:
        return None
        
    with ThreadPoolExecutor(max_workers=min(4, len(raw_frames))) as executor:
        processed_frames = list(executor.map(
            lambda x: (x[0], preprocess_frame_for_ocr(x[1])),
            raw_frames
        ))
        
    grouped: Dict[str, Dict[str, Any]] = {}
    
    for t, frame in processed_frames:
        h, w = frame.shape[:2]
        raw_items = ocr_frame(ocr, frame)
        filtered = filter_subtitle_items(
            raw_items,
            frame_h=h,
            frame_w=w,
            min_conf=min_conf,
            bottom_start=bottom_start,
        )
        
        for it in filtered:
            key = _normalize_ocr_text(it["text"])
            if not key:
                continue
            g = grouped.setdefault(key, {
                "text": it["text"],
                "conf_sum": 0.0,
                "count": 0,
                "times": [],
                "boxes": []
            })
            g["conf_sum"] += it["confidence"]
            g["count"] += 1
            g["times"].append(t)
            g["boxes"].append(it["box"])
            
    candidates = []
    for key, g in grouped.items():
        avg_conf = g["conf_sum"] / max(1, g["count"])
        candidates.append({
            "text": g["text"],
            "confidence": avg_conf,
            "count": g["count"],
            "times": g["times"],
            "boxes": g["boxes"]
        })
        
    candidates.sort(key=lambda x: (x["count"], x["confidence"]), reverse=True)
    
    for c in candidates:
        if c["confidence"] >= min_conf:
            return c
            
    return None

def ocr_all_segments(
    video_path: Union[str, Path],
    segments: List[Dict[str, Any]],
    **kwargs,
) -> List[Dict[str, Any]]:
    """OCR cho toàn bộ danh sách segments."""
    ocr = MODEL_CACHE.ocr
    out = []
    for seg in segments:
        best = ocr_segment(
            video_path,
            float(seg["start"]),
            float(seg["end"]),
            ocr=ocr,
            **kwargs,
        )
        out.append({
            "id": seg.get("id"),
            "ocr_text": best["text"] if best else None,
            "ocr_conf": best["confidence"] if best else None,
            "ocr_count": best["count"] if best else 0,
        })
    return out
