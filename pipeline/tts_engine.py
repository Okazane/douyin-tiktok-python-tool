import sys
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import edge_tts

from config import (
    TTS_ENGINE, TTS_VOICE, TTS_RATE, TTS_MAX_RATE, 
    TEMP_DIR, MELO_SPEAKER, PROJECT_ROOT
)
from utils.timing import calculate_tts_rate, get_media_duration

logger = logging.getLogger(__name__)

# Singleton MeloTTS instance
_melo_model = None

def get_melo_model():
    """Khởi tạo và tái sử dụng singleton MeloTTS Vietnamese model."""
    global _melo_model
    if _melo_model is None:
        melo_dir = PROJECT_ROOT / "melo_vietnamese"
        if not melo_dir.exists():
            raise RuntimeError(f"Thư mục MeloTTS không tìm thấy tại {melo_dir}")
            
        melo_path_str = str(melo_dir)
        if melo_path_str not in sys.path:
            sys.path.insert(0, melo_path_str)
            
        from melo.api import TTS as MeloTTS
        
        config_path = str(melo_dir / "checkpoints" / "pretrain" / "config.json")
        ckpt_path = str(melo_dir / "checkpoints" / "pretrain" / "G_463000.pth")
        
        logger.info("Đang khởi động MeloTTS Vietnamese AI Model...")
        _melo_model = MeloTTS(
            language="VI",
            device="cpu",
            use_hf=False,
            config_path=config_path,
            ckpt_path=ckpt_path
        )
    return _melo_model

@dataclass
class TTSResult:
    segment_id: int
    audio_path: Path
    original_start: float
    original_end: float
    original_duration: float
    tts_duration: float
    rate_used: str

def generate_tts_melo(segments: list, output_dir: Path = None) -> list[TTSResult]:
    """Tạo âm thanh tiếng Việt chất lượng cao bằng mô hình AI MeloTTS Vietnamese."""
    if output_dir is None:
        output_dir = TEMP_DIR / 'tts'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for f in output_dir.glob("*.wav"):
        try:
            f.unlink()
        except Exception:
            pass

    model = get_melo_model()
    spk2id = model.hps.data.spk2id
    if hasattr(spk2id, MELO_SPEAKER):
        speaker_id = getattr(spk2id, MELO_SPEAKER)
    elif hasattr(spk2id, 'items'):
        speaker_id = getattr(spk2id, list(spk2id.__dict__.keys())[0], 0)
    elif isinstance(spk2id, dict):
        speaker_id = spk2id.get(MELO_SPEAKER, list(spk2id.values())[0] if spk2id else 0)
    else:
        speaker_id = 0
    
    results = []
    logger.info(f"Đang tạo giọng đọc MeloTTS Vietnamese cho {len(segments)} đoạn...")
    
    for segment in segments:
        text = segment.translated_text.strip()
        if not text:
            text = "..."
            
        target_duration = segment.end - segment.start
        output_file = output_dir / f"seg_{segment.id:04d}.wav"
        
        # Pass 1: Tạo ở tốc độ chuẩn
        try:
            model.tts_to_file(text, speaker_id, output_path=str(output_file), speed=1.0, quiet=True)
        except Exception as e:
            logger.warning(f"MeloTTS lỗi đoạn {segment.id}: {e}. Thử fallback câu đơn...")
            try:
                model.tts_to_file(text.replace("_", " "), speaker_id, output_path=str(output_file), speed=1.0, quiet=True)
            except Exception:
                pass
                
        actual = get_media_duration(output_file) if output_file.exists() else 0.5
        tts_duration = actual
        speed_used = "1.0x"
        
        # Tự động điều chỉnh tốc độ khớp với timeline video nếu câu quá dài
        if actual > target_duration * 1.1 and target_duration > 0.3:
            needed_speed = min(1.8, max(0.8, round(actual / target_duration, 2)))
            try:
                model.tts_to_file(text, speaker_id, output_path=str(output_file), speed=needed_speed, quiet=True)
                tts_duration = get_media_duration(output_file)
                speed_used = f"{needed_speed}x"
            except Exception:
                pass
                
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
    """Hàm điều phối TTS chính (hỗ trợ cả MeloTTS Vietnamese và Edge-TTS)."""
    if engine == "melo":
        return generate_tts_melo(segments, output_dir)
    else:
        return asyncio.run(generate_tts_edge(segments, voice, output_dir))
