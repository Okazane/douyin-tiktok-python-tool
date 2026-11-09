import sys
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import edge_tts

from config import (
    TTS_ENGINE, TTS_VOICE, TTS_RATE, TTS_MAX_RATE, 
    TEMP_DIR, PROJECT_ROOT
)
from utils.timing import calculate_tts_rate, get_media_duration

logger = logging.getLogger(__name__)

# Singleton VieNeu-TTS instance
_vieneu_model = None

def get_vieneu_model(mode: str = "v3nano"):
    """Khởi tạo và tái sử dụng singleton VieNeu-TTS Vietnamese AI model (ONNX Runtime CPU)."""
    global _vieneu_model
    if _vieneu_model is None:
        logger.info("Đang khởi động VieNeu-TTS Vietnamese AI Model (ONNX CPU)...")
        from vieneu import Vieneu
        _vieneu_model = Vieneu(mode=mode)
    return _vieneu_model

# Mapping giọng đọc VieNeu theo vai
VIENEU_ROLE_VOICE_MAP = {
    "host": "Minh Quân",
    "guest_female": "Trúc Ly",
    "guest_male": "Đức Trí",
    "child": "Mỹ Duyên"
}

@dataclass
class TTSResult:
    segment_id: int
    audio_path: Path
    original_start: float
    original_end: float
    original_duration: float
    tts_duration: float
    rate_used: str

def generate_tts_vieneu(segments: list, voice: str = "Minh Quân", output_dir: Path = None) -> list[TTSResult]:
    """Tạo âm thanh tiếng Việt chất lượng cao bằng mô hình AI VieNeu-TTS v3 (Local ONNX CPU)."""
    if output_dir is None:
        output_dir = TEMP_DIR / 'tts'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for f in output_dir.glob("*.wav"):
        try:
            f.unlink()
        except Exception:
            pass

    model = get_vieneu_model()
    results = []
    logger.info(f"Đang tạo giọng đọc VieNeu-TTS cho {len(segments)} đoạn...")
    
    for segment in segments:
        text = segment.translated_text.strip()
        if not text:
            text = "..."
            
        role = getattr(segment, "role", "host")
        seg_voice = VIENEU_ROLE_VOICE_MAP.get(role, voice or "Minh Quân")
            
        target_duration = segment.end - segment.start
        output_file = output_dir / f"seg_{segment.id:04d}.wav"
        
        try:
            audio = model.infer(text=text, voice=seg_voice)
            model.save(audio, str(output_file))
        except Exception as e:
            logger.warning(f"VieNeu-TTS lỗi đoạn {segment.id}: {e}. Fallback câu đơn...")
            try:
                audio = model.infer(text=text.replace("_", " "), voice=seg_voice)
                model.save(audio, str(output_file))
            except Exception:
                pass
                
        actual = get_media_duration(output_file) if output_file.exists() else 0.5
        tts_duration = actual
        speed_used = "1.0x"
        
        results.append(TTSResult(
            segment_id=segment.id,
            audio_path=output_file,
            original_start=segment.start,
            original_end=segment.end,
            original_duration=target_duration,
            tts_duration=tts_duration,
            rate_used=speed_used
        ))
        
    return results

async def _generate_single_edge(
    text: str,
    output_path: Path,
    voice: str,
    rate: str,
    pitch: str = "+0Hz",
    target_duration: float = 1.0,
    max_retries: int = 3,
    ssml_style: str | None = None,
) -> None:
    """Tạo audio Edge-TTS với cơ chế thử lại, ngắt kết nối treo & fallback an toàn tuyệt đối."""
    import random
    clean_text = (text or "").strip()
    if not clean_text or len(clean_text) == 0:
        from utils.timing import generate_silence
        generate_silence(max(0.1, target_duration), output_path)
        return

    # ── Wrap SSML nếu có style cảm xúc (cheerful, sad, ...) ──
    if ssml_style:
        tts_input = (
            f'<speak xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" version="1.0" xml:lang="vi-VN">'
            f'<voice name="{voice}">'
            f'<mstts:express-as style="{ssml_style}" styledegree="1.5">{clean_text}</mstts:express-as>'
            f'</voice></speak>'
        )
    else:
        tts_input = clean_text

    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(
                tts_input,
                voice,
                rate=rate,
                pitch=pitch,
                connect_timeout=6,
                receive_timeout=20,
            )
            await asyncio.wait_for(communicate.save(str(output_path)), timeout=22.0)
            if output_path.exists() and output_path.stat().st_size > 200:
                return

        except Exception as e:
            if output_path.exists() and output_path.stat().st_size <= 200:
                try:
                    output_path.unlink()
                except Exception:
                    pass
            # Log kèm type lỗi để dễ debug sau này
            logger.warning(
                f"Lỗi tạo Edge-TTS ({voice}, rate={rate}, pitch={pitch}) lần {attempt + 1}/{max_retries} "
                f"cho câu '{clean_text[:25]}': [{type(e).__name__}] {e}"
            )
            if attempt < max_retries - 1:
                # Jitter ngẫu nhiên tránh nhiều coroutine retry cùng lúc (thundering herd)
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(1.0 * (attempt + 1) + jitter)
            else:
                logger.warning(f"Tạo khoảng lặng an toàn cho câu '{clean_text[:25]}' sau {max_retries} lần thử lỗi")
                from utils.timing import generate_silence
                generate_silence(max(0.1, target_duration), output_path)
                return

# Số lượng segment Edge-TTS tạo đồng thời tối ưu
EDGE_TTS_CONCURRENCY = 3

async def _process_one_edge_segment(segment, voice: str, output_dir: Path, semaphore: asyncio.Semaphore) -> TTSResult:
    """Xử lý 1 segment Edge-TTS (kèm phân vai giọng đọc Multi-Speaker & điều chỉnh tốc độ/pitch)."""
    async with semaphore:
        target_duration = max(0.1, segment.end - segment.start)
        output_file = output_dir / f"seg_{segment.id:04d}.mp3"
        text = segment.translated_text
        role = getattr(segment, "role", "host")

        # ─── Phân vai giọng đọc & Pitch Shifting (Multi-Speaker) ───
        if role == "guest_female":
            seg_voice = "vi-VN-HoaiMyNeural"
            seg_pitch = "+0Hz"
            base_rate = "+15%"
        elif role == "guest_male":
            seg_voice = "vi-VN-NamMinhNeural"
            seg_pitch = "-12Hz"  # Trầm hơn để phân biệt với host
            base_rate = "+15%"
        elif role == "child":
            seg_voice = "vi-VN-HoaiMyNeural"
            seg_pitch = "+20Hz"  # Giọng nhí
            base_rate = "+20%"
        else:
            seg_voice = voice  # Mặc định: theo kênh
            seg_pitch = "+0Hz"
            base_rate = "+15%"

        # ─── SSML Cảm xúc: thêm cheerful cho câu vui/hào hứng (dấu !) ───
        ssml_style = None
        if seg_voice == "vi-VN-HoaiMyNeural" and text.rstrip().endswith("!"):
            ssml_style = "cheerful"


        await _generate_single_edge(
            text, output_file, seg_voice, base_rate, pitch=seg_pitch,
            target_duration=target_duration, ssml_style=ssml_style
        )
        actual = get_media_duration(output_file)

        rate_used = base_rate
        tts_duration = actual

        # ─── Bước 2: Nếu dài hơn slot, tăng tốc đọc (tối đa +80%) ───
        if actual > target_duration * 1.05 and target_duration > 0.3:
            new_rate = calculate_tts_rate(target_duration, actual, base_rate=15)
            await _generate_single_edge(
                text, output_file, seg_voice, new_rate, pitch=seg_pitch,
                target_duration=target_duration, ssml_style=ssml_style
            )
            tts_duration = get_media_duration(output_file)
            rate_used = new_rate

        return TTSResult(
            segment_id=segment.id,
            audio_path=output_file,
            original_start=segment.start,
            original_end=segment.end,
            original_duration=target_duration,
            tts_duration=tts_duration,
            rate_used=rate_used
        )


async def generate_tts_edge(segments: list, voice: str = None, output_dir: Path = None) -> list[TTSResult]:
    """
    Tạo audio cho toàn bộ segments bằng Edge-TTS theo cơ chế Batch 5 + nghỉ 2s giữa các batch.
    Tránh 100% việc bị Microsoft chặn hoặc nghẽn kết nối.
    """
    if voice is None:
        voice = TTS_VOICE
    if output_dir is None:
        output_dir = TEMP_DIR / 'tts'
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Xóa TOÀN BỘ file cũ để tránh dùng cache lỗi thời từ các lần chạy trước
    for file in output_dir.glob("*.mp3"):
        try:
            file.unlink()
        except Exception:
            pass

    BATCH_SIZE = 5
    results: list[TTSResult] = []
    total_segments = len(segments)
    
    # Chia danh sách segments thành các batch nhỏ
    for i in range(0, total_segments, BATCH_SIZE):
        batch = segments[i:i + BATCH_SIZE]
        semaphore = asyncio.Semaphore(len(batch))
        batch_tasks = [_process_one_edge_segment(seg, voice, output_dir, semaphore) for seg in batch]
        
        batch_res = await asyncio.gather(*batch_tasks)
        results.extend(batch_res)
        
        # Nếu chưa phải batch cuối cùng, nghỉ nhẹ 1.5s để server Microsoft giải phóng kết nối
        if i + BATCH_SIZE < total_segments:
            await asyncio.sleep(1.5)

    # Sắp xếp lại theo segment_id để đảm bảo thứ tự chính xác
    return sorted(results, key=lambda r: r.segment_id)

def generate_tts_sync(segments: list, engine: str = TTS_ENGINE, voice: str = None, output_dir: Path = None) -> list[TTSResult]:
    """Hàm điều phối TTS chính (hỗ trợ cả VieNeu-TTS Vietnamese và Edge-TTS)."""
    if engine in ("vieneu", "v3nano", "v3turbo", "melo"):
        return generate_tts_vieneu(segments, voice=voice, output_dir=output_dir)
    else:
        return asyncio.run(generate_tts_edge(segments, voice, output_dir))
