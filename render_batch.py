"""
Script batch render 2 video Douyin theo yêu cầu người dùng, chèn logo góc trái trên cùng.
"""
import sys
import time
import logging
from pathlib import Path

# Đảm bảo mã hóa UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, 'D:/Antigravity/TIKTOK')

from config import PipelineConfig, OUTPUT_DIR, DEFAULT_LOGO_PATH
from main import run_pipeline

videos = [
    {
        "id": "7677137829121501285",
        "url": "https://www.douyin.com/user/MS4wLjABAAAAfXcaa-IzpqPRlDybTjymBK88jACVyuRnwt1KH7h9wxtbnvhhtde2ZQus4iiwL8pk?from_tab_name=main&modal_id=7677137829121501285&showSubTab=compilation&showTab=post&vid=7646658815447291365",
        "output": OUTPUT_DIR / "video_1_7677137829121501285.mp4"
    },
    {
        "id": "7664529967224789753",
        "url": "https://www.douyin.com/user/MS4wLjABAAAAfXcaa-IzpqPRlDybTjymBK88jACVyuRnwt1KH7h9wxtbnvhhtde2ZQus4iiwL8pk?from_tab_name=main&modal_id=7664529967224789753&showSubTab=compilation&showTab=post&vid=7646658815447291365",
        "output": OUTPUT_DIR / "video_2_7664529967224789753.mp4"
    }
]

def main():
    print("=" * 65)
    print("   🎬 DOUYIN2TIKTOK — BATCH RENDER 2 VIDEOS (KÈM LOGO GÓC TRÁI)")
    print(f"   🖼️ Logo: {DEFAULT_LOGO_PATH} (Tồn tại: {DEFAULT_LOGO_PATH.exists()})")
    print("=" * 65)
    
    for i, v in enumerate(videos):
        print(f"\n=======================================================")
        print(f"   🚀 [{i+1}/2] ĐANG XỬ LÝ VIDEO: {v['id']}")
        print(f"   URL: {v['url']}")
        print(f"   Output: {v['output']}")
        print(f"=======================================================\n")
        
        cfg = PipelineConfig(
            input_source=v["url"],
            voice="vi-VN-NamMinhNeural",
            output_path=str(v["output"]),
            logo_path=DEFAULT_LOGO_PATH
        )
        
        t0 = time.time()
        out_vid, out_aud = run_pipeline(cfg, export_srt=True, export_audio=True)
        t_el = time.time() - t0
        
        print(f"\n✅ [{i+1}/2] HOÀN TẤT VIDEO {v['id']} TRONG {t_el:.1f}s!")
        print(f"   📁 Video: {out_vid}")
        if out_aud:
            print(f"   🎵 Audio: {out_aud}")
            
    print("\n" + "=" * 65)
    print("🎉 TOÀN BỘ 2/2 VIDEO ĐÃ ĐƯỢC RENDER HOÀN TẤT THÀNH CÔNG!")
    print("=" * 65)

if __name__ == "__main__":
    main()
