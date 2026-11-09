"""Speech-to-text using Faster-Whisper and SenseVoice-Small AI."""
import json
import math
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from faster_whisper import WhisperModel
from config import WHISPER_MODEL, MIN_WORDS_THRESHOLD, CACHE_DIR
from pipeline.model_cache import MODEL_CACHE

logger = logging.getLogger(__name__)

@dataclass
class Segment:
    """A single transcribed segment."""
    id: int
    start: float
    end: float  
    text: str
    confidence: float

@dataclass
class TranscriptResult:
    """Result of transcription process."""
    success: bool
    segments: list[Segment]
    language: str
    total_duration: float
    word_count: int
    reason: str = ""

def get_transcript_cache_path(video_path: Path, model_size: str) -> Path:
    """Lấy đường dẫn file cache transcript cho video cụ thể."""
    cache_dir = Path(video_path).parent if Path(video_path).parent.name != "temp" else CACHE_DIR
    return cache_dir / f"transcript_{Path(video_path).stem}_{model_size}.json"

def transcribe(video_path: Path, model_size: str = "medium", engine: str = "whisper") -> TranscriptResult:
    """
    Transcribe audio from video file using RAM-cached model (Faster-Whisper hoặc SenseVoice-Small).
    Kèm Transcript Cache và cơ chế Fallback an toàn.
    """
    cache_path = get_transcript_cache_path(video_path, f"{engine}_{model_size}")
    if cache_path.exists():
        try:
            res = load_transcript(cache_path)
            if res.success and len(res.segments) > 0:
                return res
        except Exception:
            pass

    # Nếu chọn engine sensevoice -> thử SenseVoice-Small trước, fallback Whisper
    if engine == "sensevoice":
        try:
            logger.info("[Transcriber] Kích hoạt SenseVoice-Small AI ASR...")
            sv_model = MODEL_CACHE.get_sensevoice()
            res = sv_model.generate(input=str(video_path), language="zh", use_itn=True)
            if res and len(res) > 0 and res[0].get("text"):
                raw_text = res[0]["text"]
                # Dọn dẹp thẻ cảm xúc và ngôn ngữ như <|zh|><|NEUTRAL|>
                import re
                clean_text = re.sub(r"<\|[^|>]+(?:\|>)?", "", raw_text).strip()
                if len(clean_text) >= MIN_WORDS_THRESHOLD:
                    from utils.ffmpeg import get_video_info
                    vinfo = get_video_info(video_path)
                    dur = vinfo.duration or 10.0
                    seg = Segment(id=0, start=0.0, end=dur, text=clean_text, confidence=0.95)
                    result = TranscriptResult(
                        success=True,
                        segments=[seg],
                        language="zh",
                        total_duration=dur,
                        word_count=len(clean_text)
                    )
                    try:
                        save_transcript(result, cache_path)
                    except Exception:
                        pass
                    return result
        except Exception as e:
            logger.warning(f"[Transcriber] SenseVoice lỗi ({e}). Tự động fallback về Faster-Whisper...")

    # Chế độ Whisper chuẩn (int8, 8 CPU threads, beam_size=3)
    model = MODEL_CACHE.get_whisper(model_size)
    
    initial_prompt = "以下是关于美食制作、农村生活、家常菜烹饪、食材采摘的视频内容，用词准确，包含常见食材、水果、调料和方言词汇。"
    segments_gen, info = model.transcribe(
        str(video_path), 
        language="zh", 
        beam_size=3,              # 3 thay vì 5: nhanh hơn ~2x, chất lượng gần như tương đương
        vad_filter=True,
        word_timestamps=False,    # Không cần word-level alignment, tiết kiệm thời gian
        condition_on_previous_text=True,  # Bối cảnh liền mạch giữa các segment
        initial_prompt=initial_prompt
    )
    
    segments = []
    word_count = 0
    total_log_prob = 0
    
    for seg in segments_gen:
        avg_logprob = getattr(seg, 'avg_logprob', -1.0)
        confidence = math.exp(avg_logprob)
        text = seg.text.strip()
        segments.append(Segment(
            id=seg.id,
            start=seg.start,
            end=seg.end,
            text=text,
            confidence=confidence
        ))
        word_count += len(text)
        total_log_prob += avg_logprob
        
    if not segments or word_count < MIN_WORDS_THRESHOLD:
        return TranscriptResult(
            success=False,
            segments=[],
            language=info.language,
            total_duration=info.duration,
            word_count=word_count,
            reason="Video không có lời nói rõ ràng"
        )
        
    avg_confidence = math.exp(total_log_prob / len(segments))
    if avg_confidence < 0.3:
        return TranscriptResult(
            success=False,
            segments=segments,
            language=info.language,
            total_duration=info.duration,
            word_count=word_count,
            reason="Chất lượng nhận diện quá thấp"
        )
        
    res = TranscriptResult(
        success=True,
        segments=segments,
        language=info.language,
        total_duration=info.duration,
        word_count=word_count
    )
    try:
        save_transcript(res, cache_path)
    except Exception:
        pass
    return res

def save_transcript(result: TranscriptResult, output_path: Path) -> Path:
    """Save transcript to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)
    return output_path

def load_transcript(path: Path) -> TranscriptResult:
    """Load transcript from JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    data['segments'] = [Segment(**seg) for seg in data['segments']]
    return TranscriptResult(**data)
