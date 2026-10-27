import sys
import subprocess
import shutil
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    # Use rich if available, otherwise plain print
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        use_rich = True
    except ImportError:
        console = None
        use_rich = False
    
    results = []
    all_ok = True
    
    # 1. Python version
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    results.append(("Python >= 3.10", py_ver, py_ok))
    
    # 2. FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            ffmpeg_ver = out.stdout.split('\n')[0] if out.stdout else "found"
            ffmpeg_ok = True
        except Exception:
            ffmpeg_ver = "error running"
            ffmpeg_ok = False
    else:
        ffmpeg_ver = "NOT FOUND"
        ffmpeg_ok = False
    results.append(("FFmpeg", ffmpeg_ver[:60], ffmpeg_ok))
    
    # 3. FFprobe
    ffprobe_path = shutil.which("ffprobe")
    results.append(("FFprobe", str(ffprobe_path) if ffprobe_path else "NOT FOUND", bool(ffprobe_path)))
    
    # 4. Pip packages
    packages = [
        ("faster_whisper", "faster-whisper"),
        ("deep_translator", "deep-translator"),
        ("edge_tts", "edge-tts"),
        ("pysubs2", "pysubs2"),
        ("yt_dlp", "yt-dlp"),
        ("rich", "rich"),
        ("click", "click"),
    ]
    
    for import_name, pip_name in packages:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, '__version__', getattr(mod, 'version', '?'))
            results.append((pip_name, str(ver), True))
        except ImportError:
            results.append((pip_name, "NOT INSTALLED", False))
    
    # 5. Font file
    font_path = Path(__file__).parent / "assets" / "fonts" / "BeVietnamPro-Bold.ttf"
    results.append(("Font Be Vietnam Pro", str(font_path.name) if font_path.exists() else "NOT FOUND", font_path.exists()))
    
    # Print results
    if use_rich:
        table = Table(title="🔍 Kiểm tra Dependencies - Douyin2TikTok")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("OK?", justify="center")
        
        for name, status, ok in results:
            icon = "[green]✅[/]" if ok else "[red]❌[/]"
            table.add_row(name, status, icon)
            if not ok:
                all_ok = False
        
        console.print(table)
    else:
        print("=== Kiểm tra Dependencies ===")
        for name, status, ok in results:
            icon = "✅" if ok else "❌"
            print(f"  {icon} {name}: {status}")
            if not ok:
                all_ok = False
    
    # Summary
    print()
    if all_ok:
        msg = "✅ Tất cả dependencies đã sẵn sàng! Chạy: python main.py <video>"
        if use_rich:
            console.print(f"[bold green]{msg}[/]")
        else:
            print(msg)
    else:
        msg_lines = [
            "❌ Một số dependencies chưa được cài đặt.",
            "",
            "Hướng dẫn cài đặt:",
        ]
        if not ffmpeg_ok:
            msg_lines.append("  FFmpeg: winget install Gyan.FFmpeg")
        # Check which pip packages are missing
        missing_pip = [name for name, status, ok in results if not ok and status == "NOT INSTALLED"]
        if missing_pip:
            msg_lines.append(f"  Pip packages: pip install {' '.join(missing_pip)}")
        if not font_path.exists():
            msg_lines.append(f"  Font: Tải Be Vietnam Pro từ Google Fonts và đặt vào {font_path.parent}")
        
        for line in msg_lines:
            if use_rich:
                console.print(f"[yellow]{line}[/]")
            else:
                print(line)
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
