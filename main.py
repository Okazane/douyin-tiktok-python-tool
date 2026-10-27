import sys
import time
import asyncio
import logging
import shutil
from pathlib import Path


# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

from config import (
    PipelineConfig, OUTPUT_DIR, TEMP_DIR,
    TTS_ENGINE, TTS_VOICE_FEMALE, TTS_VOICE_MALE,
    COVER_POSITION, COVER_PERCENT, COVER_Y_PERCENT,
    DEFAULT_BGM_PATH
)
from pipeline.downloader import download_video
from pipeline.transcriber import transcribe, save_transcript
from pipeline.translator import translate_segments
from pipeline.tts_engine import generate_tts_sync
from pipeline.audio_mixer import mix_audio
from pipeline.subtitle_gen import generate_ass, generate_srt
from pipeline.video_processor import process_video

logger = logging.getLogger(__name__)
console = Console()


def resolve_voice(voice_input: str) -> str:
    """Chuẩn hóa tên giọng: chấp nhận 'nu', 'female', 'nam', 'male' hoặc tên voice đầy đủ."""
    v = voice_input.lower().strip()
    if v in ['nu', 'female', 'hoaimy', 'hoai_my', 'giong_nu']:
        return TTS_VOICE_FEMALE
    if v in ['nam', 'male', 'namminh', 'nam_minh', 'giong_nam']:
        return TTS_VOICE_MALE
    if v.startswith('vi-vn-'):
        return voice_input
    return TTS_VOICE_FEMALE

@click.command()
@click.argument('input_source')
@click.option('--mode', '-m', type=click.Choice(['tts_with_bgm', 'subtitle_only']),
              default='tts_with_bgm', help='Chế độ: lồng tiếng TTS hoặc chỉ phụ đề')
@click.option('--tts-engine', '-te', type=click.Choice(['edge', 'melo']),
              default=TTS_ENGINE, help='Công cụ TTS: edge (chuẩn Hoài My/Nam Minh) hoặc melo (MeloTTS)')
@click.option('--cover-position', '-cp', type=click.Choice(['bottom', 'top', 'both']),
              default=COVER_POSITION, help='Vị trí che phụ đề gốc')
@click.option('--cover-percent', '-c', type=int, default=COVER_PERCENT,
              help='Phần trăm chiều cao dải che')
@click.option('--cover-y-percent', '-cy', type=int, default=COVER_Y_PERCENT,
              help='Vị trí tâm dải che (tính từ đáy lên)')
@click.option('--voice', '-v', default='male',
              help='Chọn giọng: male / nam (Nam Minh - Nam Hà Nội) hoặc female / nu (Hoài My)')

@click.option('--whisper', '-w', type=click.Choice(['tiny', 'base', 'small', 'medium']),
              default='small', help='Model Whisper')
@click.option('--output', '-o', help='Đường dẫn file đầu ra')
@click.option('--srt', is_flag=True, default=False,
              help='Xuất thêm file phụ đề .srt rời')
@click.option('--export-audio', is_flag=True, default=True,
              help='Xuất file audio lồng tiếng riêng biệt (.wav)')
@click.option('--bgm', default=str(DEFAULT_BGM_PATH),
              help='Đường dẫn hoặc URL nhạc nền (Mặc định: Nhạc chill YouTube 57 phút)')
@click.option('--no-sub', is_flag=True, default=False,
              help='Chỉ lồng tiếng, không phụ đề/không che mờ (Stream Copy siêu tốc cho video 1-2 tiếng)')
def main(input_source, mode, tts_engine, cover_position, cover_percent, cover_y_percent, voice, whisper, output, srt, export_audio, bgm, no_sub):
    """
    🎬 Douyin2TikTok — Chuyển video Douyin sang TikTok Việt Nam
    
    Tự động: che phụ đề gốc → phiên âm → dịch (Gemini AI) → lồng tiếng (Hoài My / Nam Minh) → xuất audio/video
    """
    start_time = time.time()
    resolved_voice = resolve_voice(voice)
    
    # Print banner
    console.print(Panel.fit(
        "[bold cyan]🎬 Douyin2TikTok v1.4[/]\n"
        f"[dim]Chuyển video Douyin sang TikTok Việt Nam (Gemini AI + Giọng {'Hoài My (Nữ)' if 'HoaiMy' in resolved_voice else 'Nam Minh (Nam)'} + Nhạc Chill 3-Track)[/]" +
        ("\n[bold yellow]⚡ Chế độ: Stream Copy Dub-Only (--no-sub)[/]" if no_sub else ""),
        border_style="cyan"
    ))
    
    # Validate cover_percent
    if not 5 <= cover_percent <= 50:
        console.print("[red]❌ cover-percent phải từ 5 đến 50[/]")
        sys.exit(1)
    
    # Create config
    config = PipelineConfig(
        input_source=input_source,
        mode=mode,
        tts_engine=tts_engine,
        cover_position=cover_position,
        cover_percent=cover_percent,
        cover_y_percent=cover_y_percent,
        voice=resolved_voice,
        whisper_model=whisper,
        output_path=output,
        bgm_path=bgm,
        no_sub=no_sub
    )
    
    try:
        result, standalone_audio = run_pipeline(config, srt, export_audio)
        elapsed = time.time() - start_time
        
        if result:
            console.print()
            table = Table(title="✅ Kết quả xử lý hoàn tất", border_style="green")
            table.add_column("Thuộc tính", style="cyan")
            table.add_column("Giá trị", style="white")
            table.add_row("📁 Video hoàn chỉnh", str(result))
            if standalone_audio:
                table.add_row("🎵 Audio lồng tiếng riêng", str(standalone_audio))
            table.add_row("🗣️ Công nghệ TTS", "MeloTTS Vietnamese AI (Local)" if tts_engine == "melo" else f"Edge-TTS ({voice})")
            table.add_row("🌐 Bộ dịch thuật", "Google Gemini AI (Ngữ cảnh ẩm thực)")
            table.add_row("📐 Kích thước video", "1080 × 1920")
            table.add_row("⏱️ Thời gian xử lý", f"{elapsed:.1f}s")
            console.print(table)
        else:
            console.print("[yellow]⚠️ Pipeline dừng sớm — không có output[/]")
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Đã hủy bởi người dùng[/]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Lỗi: {e}[/]")
        logging.exception("Pipeline error")
        sys.exit(1)

def run_pipeline(config: PipelineConfig, export_srt: bool = False, export_audio: bool = True) -> tuple[Path | None, Path | None]:
    # Step 1: Download
    console.print("\n[bold]📥 Bước 1/7: Tải video...[/]")
    video_path = download_video(config.input_source)
    console.print(f"   [green]✓[/] Đã tải: {video_path.name}")
    
    # Step 2: Transcribe
    console.print("\n[bold]🎤 Bước 2/7: Nhận diện giọng nói (Whisper {})...[/]".format(config.whisper_model))
    transcript = transcribe(video_path, config.whisper_model)
    
    if not transcript.success:
        console.print(f"   [yellow]⚠️ {transcript.reason}[/]")
        if Confirm.ask("   Tiếp tục chỉ che phụ đề gốc (không dịch/lồng tiếng)?"):
            # Just cover and crop, no translation
            return _cover_only(video_path, config), None
        return None, None
    
    console.print(f"   [green]✓[/] Nhận diện {transcript.word_count} từ, {len(transcript.segments)} đoạn")
    save_transcript(transcript, TEMP_DIR / "transcript.json")
    
    from pipeline.downloader import get_video_metadata, extract_douyin_id
    from utils.channel_helper import get_channel_output_dir
    video_meta = get_video_metadata(video_path)
    title = video_meta.get("title", "")
    author = video_meta.get("author", "")
    is_erwa = any(kw in (title + author).lower() for kw in ["二娃", "nhị oa", "nhi oa", "erwa"])

    # Tự động gán output_path vào thư mục của từng kênh
    channel_dir = get_channel_output_dir(author, title)
    vid_id = extract_douyin_id(config.input_source) or video_path.stem
    if not config.output_path or Path(config.output_path).name == "output.mp4":
        config.output_path = str(channel_dir / f"video_{vid_id}.mp4")
    else:
        out_p = Path(config.output_path)
        if out_p.parent in [Path("output"), Path("D:/Antigravity/TIKTOK/output"), Path("D:\\Antigravity\\TIKTOK\\output"), Path(".")]:
            config.output_path = str(channel_dir / out_p.name)
        elif not out_p.is_absolute():
            config.output_path = str(channel_dir / out_p.name)

    logger.info(f"[Channel Manager] Lưu trữ tại thư mục kênh: {channel_dir.name} -> {Path(config.output_path).name}")


    # Step 2.5 & Step 2.6: Channel Profile Cache → OCR (chỉ quét kênh mới)
    from utils.channel_helper import get_channel_profile, save_channel_profile, get_default_voice_for_channel
    channel_name = channel_dir.name

    # ── Tự động chọn giọng đọc phù hợp với kênh ──
    auto_voice = get_default_voice_for_channel(channel_name)
    if config.voice == "vi-VN-NamMinhNeural" or not config.voice:
        config.voice = auto_voice
        logger.info(f"[Channel Manager] Tự động chọn giọng: {auto_voice} cho kênh '{channel_name}'")

    if config.no_sub:
        console.print("\n[bold yellow]⚡ Chế độ Dub-Only (--no-sub): Bỏ qua OCR và Dò tìm phụ đề gốc...[/]")
        active_segments = transcript.segments

    elif is_erwa:
        console.print("\n[bold green]🎯 Đã nhận diện Kênh Nhị Oa (二娃) — Khóa cứng toạ độ chuẩn: y=32.0%, h=12.0%[/]")
        config.cover_y_percent = 32.0
        config.cover_percent = 12.0
        active_segments = transcript.segments

    else:
        saved_profile = get_channel_profile(channel_name)

        if saved_profile:
            # ── Kênh đã biết: dùng profile cache, không quét OCR lại ──
            config.cover_y_percent = saved_profile["cover_y_percent"]
            config.cover_percent   = saved_profile["cover_percent"]
            # Cập nhật giọng từ profile nếu có lưu
            if "voice" in saved_profile:
                config.voice = saved_profile["voice"]
            console.print(
                f"\n[bold green]✅ Kênh đã biết — Dùng profile cache:[/] "
                f"y={config.cover_y_percent:.1f}%, h={config.cover_percent:.1f}%, "
                f"voice={config.voice}"
            )
            active_segments = transcript.segments

        else:
            # ── Kênh mới: quét OCR 1 lần rồi lưu vào cache ──
            console.print(f"\n[bold cyan]🔍 Kênh mới '{channel_name}' — Quét OCR để xác định vị trí phụ đề...[/]")
            from pipeline.subtitle_detector import detect_subtitle_band
            from pipeline.ocr_aligner import verify_subtitle_band, extract_and_fuse_segments

            detect_res = detect_subtitle_band(str(video_path))
            has_valid_ocr = False

            if detect_res.get("confidence", 0) >= 0.4:
                config.cover_y_percent = detect_res["cover_y_percent"]
                config.cover_percent   = detect_res["cover_percent"]

                sample_times = [s.start + (s.end - s.start) / 2 for s in transcript.segments[:4]]
                if verify_subtitle_band(video_path, config.cover_y_percent, config.cover_percent, sample_times):
                    has_valid_ocr = True
                    console.print(f"   [green]✓[/] Xác nhận toạ độ phụ đề chuẩn: y={config.cover_y_percent:.1f}%, h={config.cover_percent:.1f}%")
                else:
                    console.print(f"   [yellow]![/] Video không có phụ đề cứng rõ nét, giữ toạ độ: y={config.cover_y_percent:.1f}%")
            else:
                console.print(f"   [yellow]![/] Dùng vị trí mặc định: y={config.cover_y_percent}%, h={config.cover_percent}%")

            # ── Lưu profile vào cache để lần sau không quét lại ──
            save_channel_profile(channel_name, config.cover_y_percent, config.cover_percent, config.voice)

            # Step 2.6: OCR ⇄ Whisper Fusion (chỉ khi kênh mới có phụ đề rõ nét)
            active_segments = transcript.segments
            if has_valid_ocr:
                console.print("\n[bold]🧩 Bước 2.6/7: Dung hợp ngữ âm Pinyin (OCR ⇄ Whisper)...[/]")
                active_segments = extract_and_fuse_segments(
                    video_path, transcript.segments,
                    config.cover_y_percent, config.cover_percent
                )


    # Step 3: Contextual Translation + AI Proofread
    if video_meta.get("title"):
        console.print(f"\n[bold]🌐 Bước 3.1/7: Dịch sang tiếng Việt (Gemini AI + Ngữ cảnh: '{video_meta.get('title')[:40]}...')...[/]")
    else:
        console.print("\n[bold]🌐 Bước 3.1/7: Dịch sang tiếng Việt (Gemini AI)...[/]")
    console.print("   [bold]✏️  Bước 3.2/7: AI Senior Editor tự động thẩm định & tinh chỉnh bản dịch...[/]")
    
    translated = translate_segments(active_segments, video_context=video_meta)
    console.print(f"   [green]✓[/] Đã dịch & thẩm định xong {len(translated)} đoạn thoại")
    
    # Show preview of first 3 segments
    for seg in translated[:3]:
        console.print(f"   [dim]{seg.original_text} → {seg.translated_text}[/]")
    if len(translated) > 3:
        console.print(f"   [dim]... và {len(translated) - 3} đoạn nữa[/]")
    
    # Step 4: Closed-Loop Adaptive TTS
    tts_results = None
    if config.mode == "tts_with_bgm":
        engine_label = "MeloTTS Vietnamese AI" if config.tts_engine == "melo" else f"Edge-TTS ({config.voice})"
        console.print(f"\n[bold]🗣️ Bước 4/7: Tạo giọng đọc ({engine_label}) kèm Thích ứng thời lượng...[/]")
        tts_dir = TEMP_DIR / f"tts_{video_path.stem}"
        tts_results = generate_tts_sync(translated, engine=config.tts_engine, voice=config.voice, output_dir=tts_dir)

        console.print(f"   [green]✓[/] Đã tạo {len(tts_results)} đoạn TTS ({config.tts_engine})")
    else:
        console.print("\n[bold]⏭️ Bước 4/7: Bỏ qua TTS (chế độ chỉ phụ đề)[/]")
    
    # Step 5: Mix audio & Export standalone audio
    console.print("\n[bold]🎵 Bước 5/7: Hòa âm 3-Track (Tiếng môi trường + Nhạc Chill YouTube + Giọng đọc)...[/]")
    mixed_audio, scheduled_segments = mix_audio(video_path, tts_results, config.mode, bgm_path=config.bgm_path)
    console.print(f"   [green]✓[/] Audio tổng hợp: {mixed_audio.name}")
    
    # Cập nhật timeline cho phụ đề nếu có sử dụng Global Scheduler
    if scheduled_segments and config.mode != "subtitle_only":
        for seg, sched in zip(translated, scheduled_segments):
            seg.start = sched["start"]
            # Dùng effective_duration (sau atempo) thay vì duration gốc
            eff_dur = sched.get("effective_duration", sched["duration"])
            seg.end = sched["start"] + eff_dur
        console.print("   [green]✓[/] Đã đồng bộ timeline phụ đề với Global Scheduler")

    standalone_audio = None
    if export_audio and config.output_path:
        out_dir = Path(config.output_path).parent
        stem = Path(config.output_path).stem
        standalone_audio = out_dir / f"{stem}_audio.wav"
        shutil.copy2(mixed_audio, standalone_audio)
        console.print(f"   [green]✓[/] File Audio riêng biệt: {standalone_audio.name}")
    
    # Step 6 & 7: Xuất Video Final
    if config.no_sub:
        console.print("\n[bold]🔥 Bước 7/7: Xuất video Stream Copy siêu tốc (-c:v copy, không nén lại hình)...[/]")
        from pipeline.video_processor import remux_video_with_audio
        output = remux_video_with_audio(
            video_path, mixed_audio,
            output_path=Path(config.output_path) if config.output_path else None
        )
        console.print(f"   [green]✓[/] Video hoàn tất: {output.name}")
        return output, standalone_audio

    # Step 6: Generate subtitles
    from utils.ffmpeg import get_video_info
    v_info = get_video_info(video_path)
    console.print("\n[bold]📝 Bước 6/7: Tạo phụ đề (đặt trực tiếp bên trong video)...[/]")
    
    from pipeline.subtitle_gen import calculate_sub_margin
    margin_v = calculate_sub_margin(v_info.width, v_info.height, cover_y_percent=config.cover_y_percent, cover_percent=config.cover_percent)
    subtitle_path = generate_ass(translated, video_size=(v_info.width, v_info.height), margin_v=margin_v)
    console.print(f"   [green]✓[/] Phụ đề ASS: {subtitle_path.name}")
    
    if export_srt:
        srt_path = generate_srt(translated, Path(config.output_path).with_suffix('.srt') if config.output_path else None)
        console.print(f"   [green]✓[/] Phụ đề SRT: {srt_path.name}")
    
    # Step 7: Process video with Smart Timeline Blur
    console.print("\n[bold]🔥 Bước 7/7: Xuất video final (kèm Smart Timeline Blur)...[/]")
    cover_config = {
        'cover_position': config.cover_position,
        'cover_percent': config.cover_percent,
        'cover_y_percent': config.cover_y_percent,
        'cover_mode': config.cover_mode,
        'logo_path': config.logo_path,
    }
    
    # --- Validate Safe Zone ---
    from config import TIKTOK_UNSAFE_BOTTOM_PERCENT
    band_bottom_pct = config.cover_y_percent - (config.cover_percent / 2)
    if band_bottom_pct < TIKTOK_UNSAFE_BOTTOM_PERCENT:
        console.print(f"   [yellow]⚠️ CẢNH BÁO:[/] Dải phụ đề (cách đáy {band_bottom_pct}%) lấn vào vùng UI TikTok ({TIKTOK_UNSAFE_BOTTOM_PERCENT}%)!")
    # --------------------------
    output = process_video(
        video_path, mixed_audio, subtitle_path,
        config=cover_config,
        output_path=Path(config.output_path) if config.output_path else None,
        segments=translated
    )
    console.print(f"   [green]✓[/] Video: {output.name}")
    
    return output, standalone_audio


def _cover_only(video_path: Path, config: PipelineConfig) -> Path:
    """Chỉ che phụ đề gốc + crop, không dịch/TTS."""
    from utils.ffmpeg import extract_audio
    
    audio_path = TEMP_DIR / "original_audio.wav"
    extract_audio(video_path, audio_path)
    
    # Create empty subtitle file
    import pysubs2
    empty_subs = pysubs2.SSAFile()
    empty_sub_path = TEMP_DIR / "empty.ass" 
    empty_subs.save(str(empty_sub_path))
    
    cover_config = {
        'cover_position': config.cover_position,
        'cover_percent': config.cover_percent,
        'cover_mode': config.cover_mode,
    }
    
    output = process_video(
        video_path, audio_path, empty_sub_path,
        config=cover_config,
        output_path=Path(config.output_path) if config.output_path else None
    )
    return output


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(TEMP_DIR / 'pipeline.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    main()
