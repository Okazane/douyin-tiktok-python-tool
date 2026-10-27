"""
Comprehensive Self-Test & Diagnostic Script for Douyin2TikTok.
Tests every module individually, then runs a full synthetic end-to-end pipeline test.
"""
import sys
import os
import time
import asyncio
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import edge_tts
from config import PROJECT_ROOT, TEMP_DIR, OUTPUT_DIR, FONT_PATH, PipelineConfig
from utils.ffmpeg import run_ffmpeg, get_video_info, extract_audio, check_ffmpeg
from utils.cache import get_cache_key, is_cached
from utils.timing import calculate_tts_rate, get_media_duration, generate_silence
from pipeline.transcriber import Segment, TranscriptResult, transcribe, save_transcript
from pipeline.translator import translate_segments, translate_single
from pipeline.tts_engine import generate_tts_sync
from pipeline.audio_mixer import mix_audio
from pipeline.subtitle_gen import generate_ass, generate_srt
from pipeline.video_processor import process_video
from main import run_pipeline

def test_imports_and_ffmpeg():
    print("\n--- [1/5] Kiểm tra Hệ thống & FFmpeg ---")
    assert check_ffmpeg(), "FFmpeg không tìm thấy trong PATH!"
    print("  [PASS] FFmpeg & FFprobe sẵn sàng")
    assert FONT_PATH.exists(), f"Font không tìm thấy tại {FONT_PATH}"
    print(f"  [PASS] Font Be Vietnam Pro tồn tại: {FONT_PATH.name}")

def test_translation():
    print("\n--- [2/5] Kiểm tra Module Dịch thuật (deep-translator) ---")
    zh_text = "大家好，今天我们来学习编程。"
    vi_text = translate_single(zh_text)
    assert vi_text and len(vi_text) > 0, "Dịch thuật trả về kết quả rỗng!"
    print(f"  [PASS] zh: '{zh_text}' -> vi: '{vi_text}'")

def test_tts():
    print("\n--- [3/5] Kiểm tra Module TTS (Edge-TTS) ---")
    test_file = TEMP_DIR / "test_tts.mp3"
    async def _gen():
        comm = edge_tts.Communicate("Xin chào đây là kiểm tra giọng đọc tiếng Việt", "vi-VN-HoaiMyNeural")
        await comm.save(str(test_file))
    asyncio.run(_gen())
    assert test_file.exists() and test_file.stat().st_size > 1000, "File TTS không hợp lệ!"
    duration = get_media_duration(test_file)
    print(f"  [PASS] Tạo giọng đọc thành công (thời lượng: {duration:.2f}s, size: {test_file.stat().st_size} bytes)")

def test_subtitle_and_video_processor():
    print("\n--- [4/5] Kiểm tra Module Phụ đề & Video Processor ---")
    dummy_segments = [
        type('Seg', (), {'id': 0, 'start': 0.0, 'end': 2.5, 'translated_text': 'Xin chào các bạn'})(),
        type('Seg', (), {'id': 1, 'start': 2.6, 'end': 4.5, 'translated_text': 'Hôm nay chúng ta cùng lập trình'})()
    ]
    ass_file = TEMP_DIR / "test_sub.ass"
    generate_ass(dummy_segments, ass_file)
    assert ass_file.exists() and ass_file.stat().st_size > 100, "Tạo file ASS thất bại!"
    print(f"  [PASS] File ASS tạo thành công: {ass_file.name}")

    # Generate a 5-second synthetic video with audio
    synth_video = TEMP_DIR / "synth_raw.mp4"
    synth_audio = TEMP_DIR / "synth_audio.wav"
    generate_silence(5.0, synth_audio)
    
    cmd = [
        "ffmpeg", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=5:r=30",
        "-i", str(synth_audio),
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        "-y", str(synth_video)
    ]
    run_ffmpeg(cmd, "create synth video")
    assert synth_video.exists(), "Tạo video giả lập thất bại!"
    
    info = get_video_info(synth_video)
    assert info.width == 720 and info.height == 1280, f"Kích thước video không đúng: {info.width}x{info.height}"
    print(f"  [PASS] Video giả lập {info.width}x{info.height} ({info.duration:.1f}s) tạo thành công")

    # Test processing video (cover + crop + burn ASS)
    out_video = TEMP_DIR / "test_proc_out.mp4"
    process_video(synth_video, synth_audio, ass_file, output_path=out_video)
    assert out_video.exists() and out_video.stat().st_size > 1000, "Process video thất bại!"
    out_info = get_video_info(out_video)
    assert out_info.width == 1080 and out_info.height == 1920, f"Output video kích thước sai: {out_info.width}x{out_info.height}"
    print(f"  [PASS] Video hoàn thành xử lý chuẩn 1080x1920 ({out_info.duration:.1f}s)")

def test_full_end_to_end():
    print("\n--- [5/5] Kiểm tra End-to-End Pipeline hoàn chỉnh ---")
    # Step 1: Create a realistic Chinese speech audio via Edge-TTS (zh-CN)
    cn_audio = TEMP_DIR / "cn_speech.mp3"
    async def _gen_cn():
        text = "大家好！今天我们来聊一聊人工智能的发展。"
        comm = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await comm.save(str(cn_audio))
    asyncio.run(_gen_cn())
    cn_duration = get_media_duration(cn_audio)
    print(f"  -> Đã tạo âm thanh tiếng Trung thử nghiệm ({cn_duration:.2f}s)")

    # Step 2: Combine with synthetic vertical video
    test_e2e_input = TEMP_DIR / "e2e_input.mp4"
    cmd = [
        "ffmpeg", "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1080x1920:d={cn_duration + 0.5}:r=30",
        "-i", str(cn_audio),
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        "-y", str(test_e2e_input)
    ]
    run_ffmpeg(cmd, "create e2e input video")
    print("  -> Đã đóng gói video test đầu vào (1080x1920 có tiếng Trung)")

    # Step 3: Run pipeline with Whisper STT, Translate, TTS, Mix, Sub, Render
    test_e2e_output = OUTPUT_DIR / "e2e_verified_output.mp4"
    config = PipelineConfig(
        input_source=str(test_e2e_input),
        mode="tts_with_bgm",
        cover_position="bottom",
        cover_percent=20,
        voice="vi-VN-HoaiMyNeural",
        whisper_model="small",
        output_path=str(test_e2e_output)
    )
    
    result = run_pipeline(config, export_srt=True)
    assert result and Path(result).exists(), "Pipeline hoàn thành nhưng không tìm thấy file output!"
    
    final_info = get_video_info(Path(result))
    assert final_info.width == 1080 and final_info.height == 1920, f"Độ phân giải output không đúng: {final_info.width}x{final_info.height}"
    assert final_info.has_audio, "Video output không có luồng audio!"
    
    srt_file = Path(result).with_suffix(".srt")
    assert srt_file.exists(), "Không tìm thấy file .srt được xuất!"
    
    print(f"\n  [PASS] Pipeline E2E hoàn thành xuất sắc!")
    print(f"  -> File xuất: {result} ({final_info.width}x{final_info.height}, {final_info.duration:.1f}s, size: {Path(result).stat().st_size} bytes)")
    print(f"  -> File SRT: {srt_file}")

def main():
    print("=========================================================")
    print("   KIỂM TRA TOÀN DIỆN DỰ ÁN DOUYIN2TIKTOK (SELF-TEST)")
    print("=========================================================")
    start_t = time.time()
    
    test_imports_and_ffmpeg()
    test_translation()
    test_tts()
    test_subtitle_and_video_processor()
    test_full_end_to_end()
    
    elapsed = time.time() - start_t
    print("\n=========================================================")
    print(f"🎉 TẤT CẢ 5/5 BÀI KIỂM TRA ĐÃ VƯỢT QUA TRONG {elapsed:.1f}s! DỰ ÁN HOẠT ĐỘNG HOÀN HẢO!")
    print("=========================================================")

if __name__ == "__main__":
    main()
