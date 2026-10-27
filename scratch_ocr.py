import json, cv2, easyocr, sys
from pathlib import Path

print('Loading transcript...')
with open('D:/Antigravity/TIKTOK/temp/transcript.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find a segment with a decent length (e.g., > 2 seconds)
best_seg = None
for seg in data['segments']:
    if seg['end'] - seg['start'] > 2.0:
        best_seg = seg
        break
if not best_seg:
    best_seg = data['segments'][0]

mid_time = (best_seg['start'] + best_seg['end']) / 2
print(f"Found speech segment: {best_seg['start']} - {best_seg['end']}. Mid time: {mid_time}s")

print('Extracting frame...')
cap = cv2.VideoCapture('D:/Antigravity/TIKTOK/cache/670e3b105b50cf49/source.mp4')
cap.set(cv2.CAP_PROP_POS_MSEC, mid_time * 1000)
ret, frame = cap.read()
cap.release()

if ret:
    print('Running EasyOCR...')
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    results = reader.readtext(frame, detail=1, paragraph=False)
    
    height = frame.shape[0]
    min_y = int(height * 0.25)
    max_y = int(height * 0.88)
    
    best_box_h = 0
    best_center_y = 0
    for bbox, text, prob in results:
        if prob < 0.2: continue
        y_coords = [p[1] for p in bbox]
        top, bottom = min(y_coords), max(y_coords)
        box_h = bottom - top
        center_y = top + box_h / 2
        
        if min_y < center_y < max_y and height * 0.015 < box_h < height * 0.15:
            best_center_y = center_y
            best_box_h = box_h
            print(f'Found text: {text} at center_y={center_y}, h={box_h}')
            break
            
    if best_center_y > 0:
        cover_y_percent = (height - best_center_y) / height * 100
        cover_percent = (best_box_h * 1.8) / height * 100
        print(f'Calculated cover_y_percent: {cover_y_percent:.1f}, cover_percent: {cover_percent:.1f}')
        
        # Now run process_video manually!
        import sys
        sys.path.insert(0, 'D:/Antigravity/TIKTOK')
        from pipeline.video_processor import process_video
        from pipeline.subtitle_gen import generate_ass
        
        # 1. Regenerate subtitles with correct margin!
        from pipeline.subtitle_gen import calculate_sub_margin
        margin_v = calculate_sub_margin(1080, 1920, cover_y_percent=cover_y_percent, cover_percent=cover_percent)
        print(f'Regenerating ASS with margin_v={margin_v}...')
        subtitle_path = generate_ass(data, video_size=(1080, 1920), margin_v=margin_v)
        
        # 2. Process video
        print('Processing video...')
        config = {'cover_y_percent': cover_y_percent, 'cover_percent': cover_percent, 'cover_mode': 'boxblur', 'cover_position': 'bottom'}
        out = process_video(Path('D:/Antigravity/TIKTOK/cache/670e3b105b50cf49/source.mp4'), Path('D:/Antigravity/TIKTOK/temp/mixed_audio.wav'), subtitle_path, config=config, output_path=Path('D:/Antigravity/TIKTOK/output/output.mp4'))
        print('Done:', out)
else:
    print('Failed to extract frame')
