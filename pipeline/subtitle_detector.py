import logging
import cv2
import numpy as np
from pathlib import Path
from pipeline.model_cache import MODEL_CACHE
from pipeline.vision_ocr import ocr_frame

logger = logging.getLogger(__name__)

def extract_frames(video_path: str, num_frames: int = 5) -> list[np.ndarray]:
    """Trích xuất một số frame rải rác từ video."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Không thể mở video {video_path}")
        return []
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        return []
        
    step = total_frames // (num_frames + 2)
    frames = []
    
    for i in range(1, num_frames + 1):
        frame_idx = i * step
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
            
    cap.release()
    return frames

def detect_subtitle_band(video_path: str, sample_frames: int = 12) -> dict:
    """
    Tìm vị trí phụ đề gốc trong video bằng cách lấy mẫu 12 frames với PaddleOCR.
    """
    logger.info(f"[Detector] Đang tìm kiếm phụ đề gốc trên {sample_frames} frames...")
    frames = extract_frames(video_path, sample_frames)
    if not frames:
        return {"confidence": 0.0}
        
    ocr = MODEL_CACHE.ocr
    height, width = frames[0].shape[:2]
    
    # Vùng an toàn: bỏ qua top 25% và bottom 12%
    min_y = int(height * 0.25)
    max_y = int(height * 0.88)
    
    y_centers = []
    box_heights = []
    
    for i, frame in enumerate(frames):
        items = ocr_frame(ocr, frame)
        
        for it in items:
            if it["confidence"] < 0.70:
                continue
                
            box_h = it["height"]
            y_min, y_max = it["box"][1], it["box"][3]
            center_y = (y_min + y_max) / 2.0
            
            if center_y < min_y or center_y > max_y:
                continue
                
            if box_h < height * 0.015 or box_h > height * 0.15:
                continue
                
            y_centers.append(center_y)
            box_heights.append(box_h)
            logger.debug(f"Frame {i}: Found text '{it['text']}' at y={center_y:.1f}, h={box_h:.1f}")

    if not y_centers:
        logger.warning("[Detector] Không tìm thấy phụ đề phù hợp.")
        return {"confidence": 0.0}
        
    cluster_threshold = height * 0.02
    clusters = []
    for y in y_centers:
        found_cluster = False
        for cluster in clusters:
            if abs(cluster['center'] - y) < cluster_threshold:
                cluster['points'].append(y)
                cluster['center'] = sum(cluster['points']) / len(cluster['points'])
                found_cluster = True
                break
        if not found_cluster:
            clusters.append({'center': y, 'points': [y]})
            
    best_cluster = max(clusters, key=lambda c: len(c['points']))
    confidence = min(1.0, len(best_cluster['points']) * 0.6) 
    best_y = best_cluster['center']
    
    avg_h = 0
    valid_h_count = 0
    for y, h in zip(y_centers, box_heights):
        if abs(y - best_y) < cluster_threshold:
            avg_h += h
            valid_h_count += 1
            
    if valid_h_count > 0:
        avg_h /= valid_h_count
    else:
        avg_h = height * 0.05
        
    top_y = best_y - avg_h / 2
    bot_y = best_y + avg_h / 2
    
    padding_h = avg_h * 0.4
    cover_top = max(0, int(top_y - padding_h))
    cover_bottom = min(height, int(bot_y + padding_h))
    cover_h = cover_bottom - cover_top
    
    pct_top = (cover_top / height) * 100
    pct_h = (cover_h / height) * 100
    
    logger.info(f"[Detector] Đã khóa toạ độ phụ đề gốc: Center Y = {best_y:.1f}px, Dày = {avg_h:.1f}px")
    logger.info(f"[Detector] Đề xuất Cover: y={100 - pct_top - pct_h:.1f}%, h={pct_h:.1f}%")
    
    return {
        "cover_y_percent": 100 - pct_top - pct_h,
        "cover_percent": pct_h,
        "confidence": confidence
    }
