import subprocess
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

videos = [
    ("https://www.douyin.com/user/MS4wLjABAAAAn-xfulP0ymr-crrEo8ASVigaljzyCTBXK6fFIjWpNz8?from_tab_name=main&modal_id=7652667748418601913&vid=7650434462522030705", "1/3: K�nh M�o H�i Hu?c - Video 1"),
    ("https://www.douyin.com/user/MS4wLjABAAAAn-xfulP0ymr-crrEo8ASVigaljzyCTBXK6fFIjWpNz8?from_tab_name=main&modal_id=7651918019908585585&vid=7650434462522030705", "2/3: K�nh M�o H�i Hu?c - Video 2"),
    ("https://www.douyin.com/user/MS4wLjABAAAAn-xfulP0ymr-crrEo8ASVigaljzyCTBXK6fFIjWpNz8?from_tab_name=main&modal_id=7645234507196631033&vid=7650434462522030705", "3/3: K�nh M�o H�i Hu?c - Video 3")
]

print("===================================================================")
print("?? B?T �?U CH?Y TU?N T? 3 VIDEO (100% L?N LU?T - KH�NG SONG SONG)")
print("===================================================================\n")

for idx, (url, desc) in enumerate(videos, 1):
    print(f"\n=======================================================")
    print(f"?? [{idx}/{len(videos)}] �ANG RENDER: {desc}")
    print(f"?? URL: {url}")
    print(f"? Th?i gian b?t d?u: {time.strftime('%H:%M:%S')}")
    print(f"=======================================================\n")
    
    cmd = [
        sys.executable,
        "main.py",
        url
    ]
    ret = subprocess.run(cmd, cwd="D:/Antigravity/TIKTOK")
    if ret.returncode != 0:
        print(f"\n? Video {idx} ({desc}) g?p l?i (m� tho�t {ret.returncode})")
    else:
        print(f"\n? Video {idx} ({desc}) HO�N T?T TH�NH C�NG!")
    
    # Ngh? 5 gi�y gi?a c�c video d? gi?i ph�ng t�i nguy�n CPU/GPU
    time.sleep(5)

print("\n?????? �� HO�N T?T RENDER TU?N T? 3 VIDEO!")
