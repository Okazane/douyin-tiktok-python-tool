import json
from pathlib import Path
import sys
sys.path.insert(0, 'D:/Antigravity/TIKTOK')

from pipeline.transcriber import Segment
from pipeline.translator import translate_segments
from pipeline.subtitle_gen import generate_ass, calculate_sub_margin
from pipeline.video_processor import process_video

# 1. Load Whisper segments from JSON
print("1. Loading transcript...")
with open('D:/Antigravity/TIKTOK/temp/transcript.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

segments = []
for s in data['segments']:
    seg = Segment(id=s['id'], start=s['start'], end=s['end'], text=s['text'], confidence=s.get('confidence', 1.0))
    segments.append(seg)

# 2. Translate to Vietnamese via Gemini AI
print("2. Translating segments with Gemini AI (2-Pass)...")
translated = translate_segments(segments)
print(f"   Translated {len(translated)} segments.")
for s in translated[:3]:
    print(f"   - {s.original_text} -> {s.translated_text}")

# 3. Calculate margin for Y = 38.2%, Height = 6.7%
cover_y = 38.2
cover_h = 6.7
margin_v = calculate_sub_margin(1080, 1920, cover_y_percent=cover_y, cover_percent=cover_h)
print(f"3. Margin V: {margin_v}")

# 4. Generate ASS subtitles in Vietnamese
subtitle_path = generate_ass(translated, video_size=(1080, 1920), margin_v=margin_v)
print("4. Generated ASS file:", subtitle_path)

# 5. Process video with boxblur and Vietnamese subtitles
print("5. Processing video with FFmpeg...")
config = {
    'cover_y_percent': cover_y,
    'cover_percent': cover_h,
    'cover_mode': 'boxblur',
    'cover_position': 'bottom'
}
out = process_video(
    Path('D:/Antigravity/TIKTOK/cache/670e3b105b50cf49/source.mp4'),
    Path('D:/Antigravity/TIKTOK/temp/mixed_audio.wav'),
    subtitle_path,
    config=config,
    output_path=Path('D:/Antigravity/TIKTOK/output/output.mp4'),
    segments=translated
)
print("✅ SUCCESS! Final video with Vietnamese subtitles saved to:", out)
