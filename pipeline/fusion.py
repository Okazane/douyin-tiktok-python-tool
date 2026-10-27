"""
Fusion module for Whisper ASR and PaddleOCR.
Preserves numbers/culinary units and applies semantic glossary scoring.
"""
import re
import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from pypinyin import lazy_pinyin

logger = logging.getLogger(__name__)

def clean_zh_preserve_numbers(text: str) -> str:
    """
    Giữ lại chữ Hán + chữ số + ký hiệu và đơn vị ẩm thực quan trọng.
    (Tránh mất thông tin công thức như: 2勺, 500克, 180°C, 20分钟...)
    """
    pattern = r"[^\u4e00-\u9fff0-9\.°℃克千克毫升升勺碗盘杯斤两袋瓶个片块根段]"
    return re.sub(pattern, "", text or "")

def to_pinyin(text: str) -> str:
    """Chuyển text tiếng Trung sang chuỗi pinyin phân cách bằng khoảng trắng."""
    cleaned = clean_zh_preserve_numbers(text)
    if not cleaned:
        return ""
    return " ".join(lazy_pinyin(cleaned))

def pinyin_similarity(a: str, b: str) -> float:
    """Tính độ tương đồng ngữ âm giữa 2 chuỗi qua pinyin."""
    pa = to_pinyin(a)
    pb = to_pinyin(b)
    if not pa or not pb:
        return 0.0
    return SequenceMatcher(None, pa, pb).ratio()

def semantic_fusion(
    whisper_text: str,
    ocr_text: Optional[str],
    ocr_conf: float,
    whisper_conf: Optional[float] = None,
    context: str = "",
    glossary: Optional[Dict[str, str]] = None,
) -> Tuple[str, str, float]:
    """
    Quyết định dung hợp thông minh hơn:
    Trả về: (final_text, source, confidence)
    source: 'whisper' | 'ocr' | 'ambiguous'
    """
    whisper_text = (whisper_text or "").strip()
    ocr_text = (ocr_text or "").strip()
    
    # 1. Nếu không có OCR hoặc độ tự tin OCR quá thấp -> Giữ Whisper
    if not ocr_text or ocr_conf < 0.75:
        return whisper_text, "whisper", whisper_conf or 0.70
        
    cleaned_ocr = clean_zh_preserve_numbers(ocr_text)
    if len(cleaned_ocr) < 1:
        return whisper_text, "whisper", whisper_conf or 0.70
        
    # 2. Tính điểm tương đồng Pinyin
    pinyin_score = pinyin_similarity(whisper_text, ocr_text)
    
    # 3. Kiểm tra Glossary (Thuật ngữ ẩm thực)
    glossary_bonus = 0.0
    if glossary:
        for zh_term in glossary.keys():
            if zh_term in ocr_text:
                glossary_bonus += 0.12
            elif zh_term in whisper_text:
                glossary_bonus -= 0.05
                
    # 4. Tính điểm tổng hợp (Weighted Scoring)
    # OCR score dựa trên OCR conf + Pinyin match + Glossary bonus
    ocr_score = (ocr_conf * 0.45) + (pinyin_score * 0.35) + glossary_bonus
    whisper_score = ((whisper_conf or 0.75) * 0.55) + (1.0 - pinyin_score) * 0.15
    
    # 5. Đưa ra quyết định
    if ocr_score > whisper_score + 0.08 and pinyin_score >= 0.55:
        return ocr_text, "ocr", min(ocr_score, 1.0)
    elif whisper_score > ocr_score + 0.10:
        return whisper_text, "whisper", min(whisper_score, 1.0)
    else:
        # Nếu cả 2 đều suýt soát -> Ưu tiên OCR nếu pinyin match tốt
        if pinyin_score >= 0.70:
            return ocr_text, "ocr", min(ocr_score, 1.0)
        return whisper_text, "whisper", max(ocr_score, whisper_score)

def fuse_segments(
    whisper_segments: List[Dict[str, Any]],
    ocr_results: List[Dict[str, Any]],
    context: str = "",
    glossary: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Dung hợp danh sách segments giữa Whisper và OCR."""
    ocr_by_id = {
        x["id"]: x for x in ocr_results if x.get("id") is not None
    }
    
    fused = []
    corrected_count = 0
    
    for seg in whisper_segments:
        sid = seg.get("id")
        o = ocr_by_id.get(sid, {})
        
        whisper_text = seg.get("zh_text") or seg.get("text") or ""
        ocr_text = o.get("ocr_text")
        ocr_conf = float(o.get("ocr_conf") or 0.0)
        whisper_conf = seg.get("confidence")
        
        final_text, source, final_conf = semantic_fusion(
            whisper_text=whisper_text,
            ocr_text=ocr_text,
            ocr_conf=ocr_conf,
            whisper_conf=whisper_conf,
            context=context,
            glossary=glossary
        )
        
        if source == "ocr" and final_text != whisper_text:
            logger.info(f"[Semantic Fusion] Thay thế: '{whisper_text}' ➔ '{final_text}' (Conf: {final_conf:.2f})")
            corrected_count += 1
            
        new_seg = dict(seg)
        new_seg["zh_text"] = final_text
        new_seg["text_source"] = source
        new_seg["confidence"] = final_conf
        new_seg["ocr_text"] = ocr_text
        new_seg["ocr_conf"] = ocr_conf
        
        fused.append(new_seg)
        
    if corrected_count > 0:
        logger.info(f"✅ Semantic Fusion đã sửa {corrected_count}/{len(whisper_segments)} câu thoại bằng chữ OCR.")
        
    return fused
