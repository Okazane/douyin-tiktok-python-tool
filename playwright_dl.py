"""
Tải video Douyin bằng Playwright (trình duyệt thật) - V2.
Sử dụng domcontentloaded + intercept CDN requests.
"""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIE_FILE = Path("D:/Antigravity/TIKTOK/cookies.txt")
OUTPUT_DIR = Path("D:/Antigravity/TIKTOK/temp")

def parse_cookies_for_playwright(cookie_file: Path) -> list[dict]:
    content = cookie_file.read_text(encoding='utf-8').strip()
    cookies = []
    for item in content.split(';'):
        item = item.strip()
        if '=' in item:
            name, val = item.split('=', 1)
            name = name.strip()
            val = val.strip()
            if name and val:
                cookies.append({
                    'name': name, 'value': val,
                    'domain': '.douyin.com', 'path': '/',
                })
    return cookies

def download_douyin_playwright(video_url: str, output_path: Path) -> bool:
    m = re.search(r'(?:modal_id=|/video/)(\d+)', video_url)
    video_id = m.group(1) if m else None
    if not video_id:
        print(f"ERROR: Cannot extract video ID from {video_url}")
        return False
    
    canonical_url = f"https://www.douyin.com/video/{video_id}"
    print(f"Video ID: {video_id}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        
        if COOKIE_FILE.exists():
            cookies = parse_cookies_for_playwright(COOKIE_FILE)
            context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} cookies")
        
        page = context.new_page()
        
        # Collect ALL video CDN URLs from network
        video_urls = []
        def handle_response(response):
            url = response.url
            if any(cdn in url for cdn in ['douyinvod.com', 'douyincdn.com', 'bytevcloudcdn.com', 'bytecdn.cn']):
                if '.mp4' in url or 'video' in url.lower() or 'aweme' in url.lower():
                    video_urls.append(url)
        
        page.on('response', handle_response)
        
        try:
            print("Loading page (domcontentloaded)...")
            page.goto(canonical_url, wait_until='domcontentloaded', timeout=30000)
            
            # Dismiss popup "我知道了"
            time.sleep(2)
            try:
                popup_btn = page.locator('text=我知道了')
                if popup_btn.count() > 0:
                    popup_btn.first.click()
                    print("Dismissed popup")
                    time.sleep(1)
            except:
                pass
            
            # Click play if video is paused
            try:
                play_btn = page.locator('.xgplayer-start, [class*="play-icon"], [class*="PlayIcon"]')
                if play_btn.count() > 0:
                    play_btn.first.click(timeout=3000)
                    print("Clicked play")
            except:
                pass
            
            # Wait for video to start streaming
            print("Waiting for video stream...")
            for i in range(15):
                time.sleep(1)
                if video_urls:
                    print(f"  Found {len(video_urls)} CDN URLs after {i+1}s")
                    break
            
            # Method 2: Extract from SSR/RENDER_DATA
            if not video_urls:
                print("Trying SSR data extraction...")
                try:
                    ssr_data = page.evaluate('''() => {
                        const el = document.getElementById('RENDER_DATA');
                        if (el) return decodeURIComponent(el.textContent);
                        if (window._ROUTER_DATA) return JSON.stringify(window._ROUTER_DATA);
                        return null;
                    }''')
                    
                    if ssr_data:
                        found = re.findall(r'https?://[^"\'\\s]+(?:douyinvod|douyincdn|bytevcloudcdn|bytecdn)[^"\'\\s]+', ssr_data)
                        if found:
                            video_urls.extend(found)
                            print(f"  Found {len(found)} URLs from SSR data")
                except Exception as e:
                    print(f"  SSR failed: {e}")
            
            # Method 3: Extract video src from DOM
            if not video_urls:
                print("Trying DOM video element...")
                try:
                    srcs = page.evaluate('''() => {
                        const videos = document.querySelectorAll('video');
                        const srcs = [];
                        videos.forEach(v => {
                            if (v.src) srcs.push(v.src);
                            v.querySelectorAll('source').forEach(s => {
                                if (s.src) srcs.push(s.src);
                            });
                        });
                        return srcs;
                    }''')
                    if srcs:
                        video_urls.extend([s for s in srcs if s.startswith('http')])
                        print(f"  Found {len(srcs)} from video elements")
                except Exception as e:
                    print(f"  DOM failed: {e}")
            
            if video_urls:
                # Pick the best URL (prefer mp4, longest URL usually = highest quality)
                best_url = sorted(video_urls, key=len, reverse=True)[0]
                # Clean up URL encoding
                best_url = best_url.replace('\\u002F', '/').replace('\\u0026', '&')
                print(f"\nDownloading from CDN: {best_url[:120]}...")
                
                import requests
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0',
                    'Referer': 'https://www.douyin.com/',
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                }
                resp = requests.get(best_url, headers=headers, stream=True, timeout=120)
                if resp.status_code == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    total = 0
                    with open(output_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            f.write(chunk)
                            total += len(chunk)
                    size_mb = total / 1024 / 1024
                    print(f"Downloaded {size_mb:.1f} MB -> {output_path}")
                    return size_mb > 0.1
                else:
                    print(f"Download failed: HTTP {resp.status_code}")
                    # Try next URL
                    for alt_url in video_urls[1:3]:
                        alt_url = alt_url.replace('\\u002F', '/').replace('\\u0026', '&')
                        print(f"Trying alt: {alt_url[:100]}...")
                        resp2 = requests.get(alt_url, headers=headers, stream=True, timeout=60)
                        if resp2.status_code == 200:
                            with open(output_path, 'wb') as f:
                                for chunk in resp2.iter_content(chunk_size=65536):
                                    f.write(chunk)
                            return output_path.stat().st_size > 100000
            else:
                print("ERROR: No video URLs found")
                page.screenshot(path=str(OUTPUT_DIR / "debug_v2.png"))
                print(f"Screenshot saved: {OUTPUT_DIR / 'debug_v2.png'}")
                
        except Exception as e:
            print(f"ERROR: {e}")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "debug_v2.png"))
            except:
                pass
        finally:
            browser.close()
    
    return False

if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyin.com/video/7683569041939647795"
    output = OUTPUT_DIR / "source.mp4"
    if output.exists():
        output.unlink()
    
    success = download_douyin_playwright(url, output)
    if success:
        print("\nSUCCESS!")
    else:
        print("\nFAILED")
