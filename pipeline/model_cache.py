"""
Model Cache Singleton (RAM Optimized for 24GB DDR5).
Preloads Whisper, SenseVoice-Small, and OCR in memory, shared across all jobs.
"""
import logging

logger = logging.getLogger(__name__)

class ModelCache:
    """Cache models in RAM to avoid reload overhead between videos."""
    
    def __init__(self):
        self._whisper_model = None
        self._ocr_engine = None
        self._whisper_size = "medium"
        self._sensevoice_model = None
    
    def get_whisper(self, model_size: str = "medium"):
        if self._whisper_model is None or self._whisper_size != model_size:
            from faster_whisper import WhisperModel
            logger.info(f"[ModelCache] Nạp Faster-Whisper ({model_size}) vào RAM với 8 CPU threads...")
            self._whisper_size = model_size
            self._whisper_model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=8,
                num_workers=2
            )
        return self._whisper_model

    def get_sensevoice(self):
        """SenseVoice-Small AI (Alibaba FunAudioLLM) - Cực nhanh, nhận diện cảm xúc & tiếng Trung."""
        if self._sensevoice_model is None:
            from funasr import AutoModel
            logger.info("[ModelCache] Nạp SenseVoice-Small AI (HuggingFace, CPU) vào RAM...")
            self._sensevoice_model = AutoModel(
                model='FunAudioLLM/SenseVoiceSmall',
                hub='hf',
                device='cpu',
                disable_update=True
            )
        return self._sensevoice_model
    
    @property
    def ocr(self):
        if self._ocr_engine is None:
            import easyocr
            logger.info("[ModelCache] Nạp EasyOCR (ch_sim, en) vào RAM...")
            self._ocr_engine = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        return self._ocr_engine

# Singleton instance
MODEL_CACHE = ModelCache()
