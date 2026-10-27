# -*- coding: utf-8 -*-
"""
Global Voice Scheduler v2 - Two-Pass with Drift Recovery.

Dieu phoi timeline toan cuc cho TTS segments:
1. Moi cau duoc noi TRON VEN (khong cat)
2. Khong cau nao chong lan
3. Dong bo voi video goc (drift <= max_drift) bang cach tang toc phat (atempo)
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

MAX_ATEMPO = 1.8  # Toc do phat toi da (1.8x) - van nghe ro rang
MIN_ATEMPO = 1.0  # Toc do phat toi thieu (binh thuong)

def schedule_voice_timeline(
    tts_results: List[Any],
    max_drift: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Phan bo timeline toan cuc voi Drift Recovery.
    
    Thuat toan:
    - Khi drift < max_drift: phat audio binh thuong (atempo=1.0)
    - Khi drift >= max_drift: tang toc phat (atempo > 1.0) de keo sync lai
    - atempo duoc tinh sao cho sau khi phat xong, drift giam ve gan 0
    - Gioi han atempo <= MAX_ATEMPO (1.8x) de giu chat luong nghe
    """
    if not tts_results:
        return []
    
    scheduled = []
    prev_end = 0.0
    buffer = 0.05  # 50ms buffer giua cac cau
    
    for res in tts_results:
        ideal_start = res.original_start
        ideal_end = res.original_end
        tts_dur = res.tts_duration
        slot_dur = res.original_duration
        
        # Thoi diem som nhat co the bat dau (sau cau truoc + buffer)
        earliest_start = prev_end + buffer if prev_end > 0 else ideal_start
        
        # Bat dau tai thoi diem ly tuong hoac muon hon (neu bi chen)
        actual_start = max(ideal_start, earliest_start)
        
        # Tinh drift hien tai
        drift = actual_start - ideal_start
        
        # --- DRIFT RECOVERY ---
        # Neu drift vuot nguong, tang toc phat de keo sync lai
        atempo = 1.0
        effective_duration = tts_dur
        
        if drift > max_drift and tts_dur > 0.3:
            # Muc tieu: sau khi phat xong, drift con lai <= max_drift * 0.5
            # Ta can phat xong som hon, nen tang toc
            # ideal_end_time = ideal_start + slot_dur (thoi diem ly tuong ket thuc)
            # actual_start da bi tre, nen ta can phat nhanh hon
            
            # Thoi luong toi da cho phep de giu sync
            # = khoang cach tu actual_start den ideal_end + 1 chut du
            target_end = ideal_start + slot_dur + (max_drift * 0.5)
            available_time = max(0.3, target_end - actual_start)
            
            if tts_dur > available_time:
                atempo = min(MAX_ATEMPO, tts_dur / available_time)
                effective_duration = tts_dur / atempo
            
        elif tts_dur > slot_dur * 1.3 and slot_dur > 0.3:
            # Chua vuot nguong drift nhung cau nay dai hon slot nhieu
            # Tang toc nhe de tranh tich luy drift
            target_dur = slot_dur * 1.2  # Cho phep tran 20% slot
            if tts_dur > target_dur:
                atempo = min(MAX_ATEMPO, tts_dur / target_dur)
                effective_duration = tts_dur / atempo
        
        scheduled.append({
            "file": str(res.audio_path),
            "start": actual_start,
            "duration": tts_dur,              # Thoi luong goc cua file TTS
            "effective_duration": effective_duration,  # Thoi luong thuc sau atempo
            "allowed_duration": effective_duration,    # Cho audio_ffmpeg biet gioi han
            "slot_duration": slot_dur,
            "atempo": round(atempo, 3),
            "drift": round(drift, 2),
        })
        
        prev_end = actual_start + effective_duration
    
    # --- LOG ---
    if scheduled:
        max_d = max(s["drift"] for s in scheduled)
        avg_d = sum(s["drift"] for s in scheduled) / len(scheduled)
        sped_up = sum(1 for s in scheduled if s["atempo"] > 1.0)
        max_tempo = max(s["atempo"] for s in scheduled)
        logger.info(
            f"[Scheduler] {len(scheduled)} doan | "
            f"Max drift={max_d:.1f}s, Avg drift={avg_d:.1f}s | "
            f"{sped_up} doan tang toc (max atempo={max_tempo:.2f}x)"
        )
    
    return scheduled
